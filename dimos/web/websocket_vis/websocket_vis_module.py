#!/usr/bin/env python3

# Copyright 2025-2026 Dimensional Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
WebSocket Visualization Module for Dimos navigation and mapping.

This module provides a WebSocket data server for real-time visualization.
The frontend is served from a separate HTML file.
"""

import asyncio
from pathlib import Path as FilePath
import threading
import time
from typing import Any
import webbrowser

import numpy as np
from dimos_lcm.std_msgs import Bool
from reactivex.disposable import Disposable
import socketio  # type: ignore[import-untyped]
from starlette.applications import Starlette
from starlette.responses import FileResponse, RedirectResponse, Response
from starlette.routing import Route
import uvicorn

from dimos.utils.data import get_data

# Path to the frontend HTML templates and command-center build
_TEMPLATES_DIR = FilePath(__file__).parent.parent / "templates"
_DASHBOARD_HTML = _TEMPLATES_DIR / "rerun_dashboard.html"
_COMMAND_CENTER_DIR = (
    FilePath(__file__).parent.parent / "command-center-extension" / "dist-standalone"
)

from dimos.constants import DEFAULT_THREAD_JOIN_TIMEOUT
from dimos.core.core import rpc
from dimos.core.module import Module, ModuleConfig
from dimos.core.stream import In, Out
from dimos.mapping.models import LatLon
from dimos.mapping.occupancy.gradient import gradient
from dimos.mapping.occupancy.inflation import simple_inflate
from dimos.msgs.geometry_msgs.PointStamped import PointStamped
from dimos.msgs.geometry_msgs.PoseStamped import PoseStamped
from dimos.msgs.geometry_msgs.Twist import Twist
from dimos.msgs.geometry_msgs.TwistStamped import TwistStamped
from dimos.msgs.geometry_msgs.Vector3 import Vector3
from dimos.msgs.nav_msgs.Odometry import Odometry
from dimos.msgs.nav_msgs.OccupancyGrid import OccupancyGrid
from dimos.msgs.nav_msgs.Path import Path
from dimos.msgs.sensor_msgs.PointCloud2 import PointCloud2
from dimos.utils.logging_config import setup_logger

from .optimized_costmap import OptimizedCostmapEncoder

logger = setup_logger()

_browser_open_lock = threading.Lock()
_browser_opened = False


class WebsocketConfig(ModuleConfig):
    port: int = 7779
    fallback_costmap_enabled: bool = True
    fallback_costmap_resolution: float = 0.2
    fallback_costmap_min_size_m: float = 20.0
    fallback_costmap_margin_m: float = 10.0
    pointcloud_costmap_enabled: bool = True
    pointcloud_costmap_resolution: float = 0.2
    pointcloud_costmap_max_hz: float = 2.0
    pointcloud_costmap_max_points: int = 50_000
    pointcloud_costmap_min_size_m: float = 20.0
    pointcloud_costmap_max_size_m: float = 40.0
    pointcloud_costmap_padding_m: float = 1.0
    pointcloud_costmap_min_z: float = -2.0
    pointcloud_costmap_max_z: float = 3.0
    pointcloud_costmap_radius_cells: int = 1


class WebsocketVisModule(Module):
    """
    WebSocket-based visualization module for real-time navigation data.

    This module provides a web interface for visualizing:
    - Robot position and orientation
    - Navigation paths
    - Costmaps
    - Interactive goal setting via mouse clicks

    Inputs:
        - robot_pose: Current robot position
        - path: Navigation path
        - global_costmap: Global costmap for visualization

    Outputs:
        - click_goal: Goal position from user clicks
    """

    config: WebsocketConfig

    # LCM inputs
    odom: In[PoseStamped]
    slam_odom: In[Odometry]
    gps_location: In[LatLon]
    path: In[Path]
    global_costmap: In[OccupancyGrid]
    local_map: In[PointCloud2]

    # LCM outputs
    goal_request: Out[PoseStamped]
    clicked_point: Out[PointStamped]
    gps_goal: Out[LatLon]
    explore_cmd: Out[Bool]
    stop_explore_cmd: Out[Bool]
    tele_cmd_vel: Out[Twist]
    movecmd_stamped: Out[TwistStamped]

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the WebSocket visualization module.

        Args:
            port: Port to run the web server on
            cfg: Optional global config for viewer settings
        """
        super().__init__(**kwargs)
        self._uvicorn_server_thread: threading.Thread | None = None
        self.sio: socketio.AsyncServer | None = None
        self.app = None
        self._broadcast_loop = None
        self._broadcast_thread = None
        self._uvicorn_server: uvicorn.Server | None = None

        self.vis_state = {}  # type: ignore[var-annotated]
        self.state_lock = threading.Lock()
        self.costmap_encoder = OptimizedCostmapEncoder(chunk_size=64)
        self._has_real_costmap = False
        self._last_pointcloud_costmap_time = 0.0
        self._last_robot_xy: tuple[float, float] | None = None

        # Track GPS goal points for visualization
        self.gps_goal_points: list[dict[str, float]] = []
        logger.info(
            f"WebSocket visualization module initialized on port {self.config.port}, GPS goal tracking enabled"
        )

    def _start_broadcast_loop(self) -> None:
        def websocket_vis_loop() -> None:
            self._broadcast_loop = asyncio.new_event_loop()  # type: ignore[assignment]
            asyncio.set_event_loop(self._broadcast_loop)
            try:
                self._broadcast_loop.run_forever()  # type: ignore[attr-defined]
            except Exception as e:
                logger.error(f"Broadcast loop error: {e}")
            finally:
                self._broadcast_loop.close()  # type: ignore[attr-defined]

        self._broadcast_thread = threading.Thread(target=websocket_vis_loop, daemon=True)  # type: ignore[assignment]
        self._broadcast_thread.start()  # type: ignore[attr-defined]

    @rpc
    def start(self) -> None:
        super().start()

        self._create_server()

        self._start_broadcast_loop()

        self._uvicorn_server_thread = threading.Thread(target=self._run_uvicorn_server, daemon=True)
        self._uvicorn_server_thread.start()

        # Only auto-open when the user chose web-based viewing.
        if self.config.g.viewer == "rerun" and self.config.g.rerun_open in ("web", "both"):
            url = f"http://localhost:{self.config.port}/"
            logger.info(f"Dimensional Command Center: {url}")

            global _browser_opened
            with _browser_open_lock:
                if not _browser_opened:
                    try:
                        webbrowser.open_new_tab(url)
                        _browser_opened = True
                    except Exception as e:
                        logger.debug(f"Failed to open browser: {e}")

        try:
            unsub = self.odom.subscribe(self._on_robot_pose)
            self.register_disposable(Disposable(unsub))
        except Exception:
            ...

        try:
            unsub = self.slam_odom.subscribe(self._on_slam_odom)
            self.register_disposable(Disposable(unsub))
        except Exception:
            ...

        try:
            unsub = self.gps_location.subscribe(self._on_gps_location)
            self.register_disposable(Disposable(unsub))
        except Exception:
            ...

        try:
            unsub = self.path.subscribe(self._on_path)
            self.register_disposable(Disposable(unsub))
        except Exception:
            ...

        try:
            unsub = self.global_costmap.subscribe(self._on_global_costmap)
            self.register_disposable(Disposable(unsub))
        except Exception:
            ...

        try:
            unsub = self.local_map.subscribe(self._on_local_map)
            self.register_disposable(Disposable(unsub))
        except Exception:
            ...

    @rpc
    def stop(self) -> None:
        if getattr(self, "_ws_stopped", False):
            return
        self._ws_stopped = True

        if self._uvicorn_server:
            self._uvicorn_server.should_exit = True

        if self.sio and self._broadcast_loop and not self._broadcast_loop.is_closed():

            async def _disconnect_all() -> None:
                await self.sio.disconnect()

            asyncio.run_coroutine_threadsafe(_disconnect_all(), self._broadcast_loop)

        if self._broadcast_loop and not self._broadcast_loop.is_closed():
            self._broadcast_loop.call_soon_threadsafe(self._broadcast_loop.stop)

        if self._broadcast_thread and self._broadcast_thread.is_alive():
            self._broadcast_thread.join(timeout=DEFAULT_THREAD_JOIN_TIMEOUT)

        if self._uvicorn_server_thread and self._uvicorn_server_thread.is_alive():
            self._uvicorn_server_thread.join(timeout=DEFAULT_THREAD_JOIN_TIMEOUT)

        super().stop()

    @rpc
    def set_gps_travel_goal_points(self, points: list[LatLon]) -> None:
        json_points = [{"lat": x.lat, "lon": x.lon} for x in points]
        self.vis_state["gps_travel_goal_points"] = json_points
        self._emit("gps_travel_goal_points", json_points)

    def _create_server(self) -> None:
        # Create SocketIO server
        self.sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")

        async def serve_index(request):  # type: ignore[no-untyped-def]
            """Serve appropriate HTML based on viewer mode."""
            if not (
                self.config.g.viewer == "rerun" and self.config.g.rerun_open in ("web", "both")
            ):
                return RedirectResponse(url="/command-center")
            return FileResponse(_DASHBOARD_HTML, media_type="text/html")

        async def serve_command_center(request):  # type: ignore[no-untyped-def]
            """Serve the command center 2D visualization (built React app)."""
            index_file = get_data("command_center.html")
            if index_file.exists():
                html = index_file.read_text(encoding="utf-8")
                html = html.replace(
                    'Ql("ws://localhost:7779")',
                    "Ql(window.location.origin)",
                )
                return Response(content=html, media_type="text/html")
            else:
                return Response(
                    content="Command center not built. Run: cd dimos/web/command-center-extension && npm install && npm run build:standalone",
                    status_code=503,
                    media_type="text/plain",
                )

        routes = [
            Route("/", serve_index),
            Route("/command-center", serve_command_center),
        ]

        starlette_app = Starlette(routes=routes)

        self.app = socketio.ASGIApp(self.sio, starlette_app)

        # Register SocketIO event handlers
        @self.sio.event  # type: ignore[untyped-decorator]
        async def connect(sid, environ) -> None:  # type: ignore[no-untyped-def]
            with self.state_lock:
                current_state = dict(self.vis_state)

            # Include GPS goal points in the initial state
            if self.gps_goal_points:
                current_state["gps_travel_goal_points"] = self.gps_goal_points

            # Force full costmap update on new connection
            self.costmap_encoder.last_full_grid = None

            await self.sio.emit("full_state", current_state, room=sid)  # type: ignore[union-attr]
            logger.info(
                f"Client {sid} connected, sent state with {len(self.gps_goal_points)} GPS goal points"
            )

        @self.sio.event  # type: ignore[untyped-decorator]
        async def click(sid, position) -> None:  # type: ignore[no-untyped-def]
            goal = PoseStamped(
                position=(position[0], position[1], 0),
                orientation=(0, 0, 0, 1),  # Default orientation
                frame_id="world",
            )
            point = PointStamped(
                x=float(position[0]),
                y=float(position[1]),
                z=0.0,
                frame_id="map",
            )
            self.goal_request.publish(goal)
            self.clicked_point.publish(point)
            logger.info(
                "Click goal published", x=round(goal.position.x, 3), y=round(goal.position.y, 3)
            )

        @self.sio.event  # type: ignore[untyped-decorator]
        async def gps_goal(sid: str, goal: dict[str, float]) -> None:
            logger.info(f"Received GPS goal: {goal}")

            # Publish the goal to LCM
            self.gps_goal.publish(LatLon(lat=goal["lat"], lon=goal["lon"]))

            # Add to goal points list for visualization
            self.gps_goal_points.append(goal)
            logger.info(f"Added GPS goal to list. Total goals: {len(self.gps_goal_points)}")

            # Emit updated goal points back to all connected clients
            if self.sio is not None:
                await self.sio.emit("gps_travel_goal_points", self.gps_goal_points)
            logger.debug(
                f"Emitted gps_travel_goal_points with {len(self.gps_goal_points)} points: {self.gps_goal_points}"
            )

        @self.sio.event  # type: ignore[untyped-decorator]
        async def start_explore(sid: str) -> None:
            logger.info("Starting exploration")
            self.explore_cmd.publish(Bool(data=True))

        @self.sio.event  # type: ignore[untyped-decorator]
        async def stop_explore(sid) -> None:  # type: ignore[no-untyped-def]
            logger.info("Stopping exploration")
            self.stop_explore_cmd.publish(Bool(data=True))

        @self.sio.event  # type: ignore[untyped-decorator]
        async def clear_gps_goals(sid: str) -> None:
            logger.info("Clearing all GPS goal points")
            self.gps_goal_points.clear()
            if self.sio is not None:
                await self.sio.emit("gps_travel_goal_points", self.gps_goal_points)
            logger.info("GPS goal points cleared and updated clients")

        @self.sio.event  # type: ignore[untyped-decorator]
        async def move_command(sid: str, data: dict[str, Any]) -> None:
            # Publish Twist if transport is configured
            if self.tele_cmd_vel and self.tele_cmd_vel.transport:
                twist = Twist(
                    linear=Vector3(data["linear"]["x"], data["linear"]["y"], data["linear"]["z"]),
                    angular=Vector3(
                        data["angular"]["x"], data["angular"]["y"], data["angular"]["z"]
                    ),
                )
                self.tele_cmd_vel.publish(twist)

            # Publish TwistStamped if transport is configured
            if self.movecmd_stamped and self.movecmd_stamped.transport:
                twist_stamped = TwistStamped(
                    ts=time.time(),
                    frame_id="base_link",
                    linear=Vector3(data["linear"]["x"], data["linear"]["y"], data["linear"]["z"]),
                    angular=Vector3(
                        data["angular"]["x"], data["angular"]["y"], data["angular"]["z"]
                    ),
                )
                self.movecmd_stamped.publish(twist_stamped)

    def _run_uvicorn_server(self) -> None:
        config = uvicorn.Config(
            self.app,  # type: ignore[arg-type]
            host=self.config.g.listen_host,
            port=self.config.port,
            log_level="error",  # Reduce verbosity
        )
        self._uvicorn_server = uvicorn.Server(config)
        self._uvicorn_server.run()

    def _on_robot_pose(self, msg: PoseStamped) -> None:
        pose_data = {"type": "vector", "c": [msg.position.x, msg.position.y, msg.position.z]}
        self._last_robot_xy = (msg.position.x, msg.position.y)
        self.vis_state["robot_pose"] = pose_data
        self._emit("robot_pose", pose_data)
        self._ensure_fallback_costmap(msg.position.x, msg.position.y)

    def _on_slam_odom(self, msg: Odometry) -> None:
        pose_data = {"type": "vector", "c": [msg.position.x, msg.position.y, msg.position.z]}
        self._last_robot_xy = (msg.position.x, msg.position.y)
        self.vis_state["robot_pose"] = pose_data
        self._emit("robot_pose", pose_data)
        self._ensure_fallback_costmap(msg.position.x, msg.position.y)

    def _on_gps_location(self, msg: LatLon) -> None:
        pose_data = {"lat": msg.lat, "lon": msg.lon}
        self.vis_state["gps_location"] = pose_data
        self._emit("gps_location", pose_data)

    def _on_path(self, msg: Path) -> None:
        points = [[pose.position.x, pose.position.y] for pose in msg.poses]
        path_data = {"type": "path", "points": points}
        self.vis_state["path"] = path_data
        self._emit("path", path_data)

    def _on_global_costmap(self, msg: OccupancyGrid) -> None:
        self._has_real_costmap = True
        costmap_data = self._process_costmap(msg)
        self.vis_state["costmap"] = costmap_data
        self._emit("costmap", costmap_data)

    def _on_local_map(self, msg: PointCloud2) -> None:
        if not self.config.pointcloud_costmap_enabled or self._has_real_costmap:
            return

        max_hz = float(self.config.pointcloud_costmap_max_hz)
        now = time.monotonic()
        if max_hz > 0 and now - self._last_pointcloud_costmap_time < 1.0 / max_hz:
            return
        self._last_pointcloud_costmap_time = now

        try:
            points = msg.points_f32()
        except Exception:
            logger.debug("Failed to decode local_map point cloud for 2D web view", exc_info=True)
            return

        costmap_data = self._pointcloud_to_costmap(points)
        if costmap_data is None:
            return

        self.vis_state["costmap"] = costmap_data
        self._emit("costmap", costmap_data)

    def _pointcloud_to_costmap(self, points: np.ndarray) -> dict[str, Any] | None:
        if points.size == 0:
            return None

        points = np.asarray(points, dtype=np.float32)
        if points.ndim != 2 or points.shape[1] < 3:
            return None

        finite = np.isfinite(points[:, 0]) & np.isfinite(points[:, 1]) & np.isfinite(points[:, 2])
        z_mask = (points[:, 2] >= self.config.pointcloud_costmap_min_z) & (
            points[:, 2] <= self.config.pointcloud_costmap_max_z
        )
        points = points[finite & z_mask]
        if len(points) == 0:
            return None

        max_points = max(1, int(self.config.pointcloud_costmap_max_points))
        if len(points) > max_points:
            stride = int(np.ceil(len(points) / max_points))
            points = points[::stride]

        if self._last_robot_xy is not None:
            center_x, center_y = self._last_robot_xy
        else:
            center_x = float((points[:, 0].min() + points[:, 0].max()) * 0.5)
            center_y = float((points[:, 1].min() + points[:, 1].max()) * 0.5)

        max_size_m = max(float(self.config.pointcloud_costmap_max_size_m), 1.0)
        half_max = max_size_m * 0.5
        in_window = (
            (points[:, 0] >= center_x - half_max)
            & (points[:, 0] <= center_x + half_max)
            & (points[:, 1] >= center_y - half_max)
            & (points[:, 1] <= center_y + half_max)
        )
        points = points[in_window]
        if len(points) == 0:
            return None

        padding = max(float(self.config.pointcloud_costmap_padding_m), 0.0)
        min_x = float(min(points[:, 0].min(), center_x) - padding)
        max_x = float(max(points[:, 0].max(), center_x) + padding)
        min_y = float(min(points[:, 1].min(), center_y) - padding)
        max_y = float(max(points[:, 1].max(), center_y) + padding)

        min_size_m = max(float(self.config.pointcloud_costmap_min_size_m), 1.0)
        if max_x - min_x < min_size_m:
            min_x = center_x - min_size_m * 0.5
            max_x = center_x + min_size_m * 0.5
        if max_y - min_y < min_size_m:
            min_y = center_y - min_size_m * 0.5
            max_y = center_y + min_size_m * 0.5

        resolution = max(float(self.config.pointcloud_costmap_resolution), 0.02)
        width = max(10, int(np.ceil((max_x - min_x) / resolution)))
        height = max(10, int(np.ceil((max_y - min_y) / resolution)))
        grid = np.full((height, width), -1, dtype=np.int8)

        ix = ((points[:, 0] - min_x) / resolution).astype(np.int32)
        iy = ((points[:, 1] - min_y) / resolution).astype(np.int32)
        valid = (ix >= 0) & (ix < width) & (iy >= 0) & (iy < height)
        ix = ix[valid]
        iy = iy[valid]
        if len(ix) == 0:
            return None

        radius = max(0, int(self.config.pointcloud_costmap_radius_cells))
        if radius == 0:
            grid[iy, ix] = 100
        else:
            for dy in range(-radius, radius + 1):
                yy = np.clip(iy + dy, 0, height - 1)
                for dx in range(-radius, radius + 1):
                    xx = np.clip(ix + dx, 0, width - 1)
                    grid[yy, xx] = 100

        grid_data = self.costmap_encoder.encode_costmap(grid, force_full=True)
        return {
            "type": "costmap",
            "grid": grid_data,
            "origin": {"type": "vector", "c": [min_x, min_y, 0]},
            "resolution": resolution,
            "origin_theta": 0,
        }

    def _ensure_fallback_costmap(self, x: float, y: float) -> None:
        if not self.config.fallback_costmap_enabled or self._has_real_costmap:
            return
        if "costmap" in self.vis_state:
            return

        resolution = max(float(self.config.fallback_costmap_resolution), 0.01)
        size_m = max(
            float(self.config.fallback_costmap_min_size_m),
            float(self.config.fallback_costmap_margin_m) * 2.0,
        )
        cells = max(10, int(size_m / resolution))
        grid = np.zeros((cells, cells), dtype=np.int8)
        grid_data = self.costmap_encoder.encode_costmap(grid, force_full=True)
        origin_x = x - (cells * resolution / 2.0)
        origin_y = y - (cells * resolution / 2.0)

        costmap_data = {
            "type": "costmap",
            "grid": grid_data,
            "origin": {"type": "vector", "c": [origin_x, origin_y, 0]},
            "resolution": resolution,
            "origin_theta": 0,
        }
        self.vis_state["costmap"] = costmap_data
        self._emit("costmap", costmap_data)

    def _process_costmap(self, costmap: OccupancyGrid) -> dict[str, Any]:
        """Convert OccupancyGrid to visualization format."""
        costmap = gradient(simple_inflate(costmap, 0.1), max_distance=1.0)
        grid_data = self.costmap_encoder.encode_costmap(costmap.grid)

        return {
            "type": "costmap",
            "grid": grid_data,
            "origin": {
                "type": "vector",
                "c": [costmap.origin.position.x, costmap.origin.position.y, 0],
            },
            "resolution": costmap.resolution,
            "origin_theta": 0,  # Assuming no rotation for now
        }

    def _emit(self, event: str, data: Any) -> None:
        if self._broadcast_loop and not self._broadcast_loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.sio.emit(event, data), self._broadcast_loop)
