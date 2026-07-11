"""Fail-closed RTAB-Map shadow integration for the HE platform."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import ctypes
from dataclasses import dataclass, field
import math
import os
from pathlib import Path as FilePath
import signal
import subprocess
import threading
import time
from typing import Any

import numpy as np
from pydantic import Field

from dimos.core.module import Module, ModuleConfig
from dimos.core.stream import In, Out
from dimos.msgs.geometry_msgs.Pose import Pose
from dimos.msgs.geometry_msgs.PoseStamped import PoseStamped
from dimos.msgs.geometry_msgs.PoseWithCovariance import PoseWithCovariance
from dimos.msgs.geometry_msgs.Twist import Twist
from dimos.msgs.geometry_msgs.TwistWithCovariance import TwistWithCovariance
from dimos.msgs.nav_msgs.OccupancyGrid import OccupancyGrid
from dimos.msgs.nav_msgs.Odometry import Odometry
from dimos.msgs.nav_msgs.Path import Path
from dimos.utils.logging_config import setup_logger

logger = setup_logger()
_LIBC = ctypes.CDLL(None)


def _terminate_with_parent() -> None:
    """Ask Linux to terminate the native runner if its DimOS worker dies."""
    if _LIBC.prctl(1, signal.SIGTERM) != 0:  # PR_SET_PDEATHSIG
        os._exit(127)
    if os.getppid() == 1:
        os.kill(os.getpid(), signal.SIGTERM)


def _stamp_seconds(header: Any) -> float:
    return float(header.stamp.sec) + float(header.stamp.nanosec) / 1_000_000_000.0


def _validated_quaternion(value: Any) -> list[float]:
    quaternion = np.asarray([value.x, value.y, value.z, value.w], dtype=np.float64)
    norm = float(np.linalg.norm(quaternion))
    if not np.all(np.isfinite(quaternion)) or norm < 1e-9:
        raise ValueError("pose contains an invalid quaternion")
    return list(quaternion / norm)


def _pose_from_ros(value: Any) -> Pose:
    position = np.asarray([value.position.x, value.position.y, value.position.z], dtype=np.float64)
    if not np.all(np.isfinite(position)):
        raise ValueError("pose contains a non-finite position")
    return Pose(position=list(position), orientation=_validated_quaternion(value.orientation))


class HEVisualSlamBridgeConfig(ModuleConfig):
    ros_node_name: str = "dimos_he_visual_slam"
    odom_topic: str = "/he/visual_odom"
    map_topic: str = "/he/visual_occupancy"
    path_topic: str = "/he/visual_path"
    odom_info_topic: str = "/he/visual_odom_info"
    map_frame: str = "he_map"
    odom_frame: str = "he_visual_odom"
    base_frame: str = "base_link"
    tf_poll_hz: float = Field(default=5.0, gt=0.0)


class HEVisualSlamBridge(Module):
    """Convert RTAB-Map ROS outputs into DimOS messages and health observations."""

    dedicated_worker = True

    config: HEVisualSlamBridgeConfig
    visual_odom: Out[Odometry]
    visual_map: Out[OccupancyGrid]
    visual_path: Out[Path]
    visual_status: Out[dict]

    def __init__(self, **config_args: Any) -> None:
        super().__init__(**config_args)
        self._node: Any | None = None
        self._executor: Any | None = None
        self._spin_thread: threading.Thread | None = None
        self._tf_buffer: Any | None = None
        self._last_tf: tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]] | None = None
        self._tracking: dict[str, Any] = {"tracking_lost": True, "inliers": 0}

    async def main(self) -> AsyncGenerator[None, None]:
        self._start_ros()
        try:
            yield
        finally:
            self._stop_ros()

    @staticmethod
    def odometry_from_ros(msg: Any) -> Odometry:
        pose = _pose_from_ros(msg.pose.pose)
        twist = msg.twist.twist
        values = [
            twist.linear.x,
            twist.linear.y,
            twist.linear.z,
            twist.angular.x,
            twist.angular.y,
            twist.angular.z,
        ]
        if not all(math.isfinite(float(value)) for value in values):
            raise ValueError("odometry contains a non-finite twist")
        return Odometry(
            ts=_stamp_seconds(msg.header),
            frame_id=msg.header.frame_id,
            child_frame_id=msg.child_frame_id,
            pose=PoseWithCovariance(pose, list(msg.pose.covariance)),
            twist=TwistWithCovariance(
                Twist(linear=values[:3], angular=values[3:]), list(msg.twist.covariance)
            ),
        )

    @staticmethod
    def occupancy_from_ros(msg: Any) -> OccupancyGrid:
        width = int(msg.info.width)
        height = int(msg.info.height)
        resolution = float(msg.info.resolution)
        cells = np.asarray(msg.data, dtype=np.int16)
        if width <= 0 or height <= 0 or cells.size != width * height:
            raise ValueError("occupancy payload does not match positive map dimensions")
        if not math.isfinite(resolution) or resolution <= 0.0:
            raise ValueError("occupancy resolution must be positive and finite")
        if np.any((cells < -1) | (cells > 100)):
            raise ValueError("occupancy cells must be in [-1, 100]")
        return OccupancyGrid(
            grid=cells.astype(np.int8).reshape(height, width),
            resolution=resolution,
            origin=_pose_from_ros(msg.info.origin),
            frame_id=msg.header.frame_id,
            ts=_stamp_seconds(msg.header),
        )

    @staticmethod
    def path_from_ros(msg: Any) -> Path:
        frame_id = msg.header.frame_id
        if not frame_id:
            raise ValueError("trajectory frame is empty")
        poses = [
            PoseStamped(
                ts=_stamp_seconds(item.header),
                frame_id=item.header.frame_id or frame_id,
                position=_pose_from_ros(item.pose).position,
                orientation=_pose_from_ros(item.pose).orientation,
            )
            for item in msg.poses
        ]
        return Path(ts=_stamp_seconds(msg.header), frame_id=frame_id, poses=poses)

    def _start_ros(self) -> None:
        try:
            from nav_msgs.msg import (
                OccupancyGrid as RosOccupancyGrid,
                Odometry as RosOdometry,
                Path as RosPath,
            )
            import rclpy
            from rclpy.duration import Duration
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.node import Node
            from rclpy.qos import qos_profile_sensor_data
            from rtabmap_msgs.msg import OdomInfo
            from tf2_ros import Buffer, TransformListener
        except ImportError as exc:
            raise RuntimeError("HEVisualSlamBridge requires ROS 2 and RTAB-Map messages") from exc

        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = Node(self.config.ros_node_name)
        self._node.create_subscription(
            RosOdometry, self.config.odom_topic, self._on_odom, qos_profile_sensor_data
        )
        self._node.create_subscription(
            RosOccupancyGrid, self.config.map_topic, self._on_map, qos_profile_sensor_data
        )
        self._node.create_subscription(
            RosPath, self.config.path_topic, self._on_path, qos_profile_sensor_data
        )
        self._node.create_subscription(
            OdomInfo, self.config.odom_info_topic, self._on_odom_info, qos_profile_sensor_data
        )
        self._tf_buffer = Buffer(cache_time=Duration(seconds=5.0))
        self._tf_listener = TransformListener(self._tf_buffer, self._node)
        self._node.create_timer(1.0 / self.config.tf_poll_hz, self._publish_tf_status)
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(target=self._spin_ros, daemon=True)
        self._spin_thread.start()

    def _spin_ros(self) -> None:
        from rclpy.executors import ExternalShutdownException

        try:
            if self._executor is not None:
                self._executor.spin()
        except ExternalShutdownException:
            pass

    def _stop_ros(self) -> None:
        if self._executor is not None:
            self._executor.shutdown()
            self._executor = None
        if self._spin_thread is not None:
            self._spin_thread.join(timeout=2.0)
            self._spin_thread = None
        if self._node is not None:
            self._node.destroy_node()
            self._node = None
        self._tf_buffer = None

    def _on_odom(self, msg: Any) -> None:
        try:
            odometry = self.odometry_from_ros(msg)
            self._tracking["odom_latency_ms"] = max(0.0, (time.time() - odometry.ts) * 1000.0)
            self.visual_odom.publish(odometry)
        except ValueError as exc:
            logger.warning("Dropping invalid visual odometry: %s", exc)

    def _on_map(self, msg: Any) -> None:
        try:
            self.visual_map.publish(self.occupancy_from_ros(msg))
        except ValueError as exc:
            logger.warning("Dropping invalid visual occupancy: %s", exc)

    def _on_path(self, msg: Any) -> None:
        try:
            self.visual_path.publish(self.path_from_ros(msg))
        except ValueError as exc:
            logger.warning("Dropping invalid visual trajectory: %s", exc)

    def _on_odom_info(self, msg: Any) -> None:
        self._tracking.update(
            {
                "tracking_lost": bool(msg.lost),
                "inliers": int(msg.inliers),
                "features": int(msg.features),
            }
        )

    def _publish_tf_status(self) -> None:
        status = {**self._tracking, "stamp": time.time(), "tf_ok": False}
        try:
            import rclpy

            transform = self._tf_buffer.lookup_transform(
                self.config.map_frame, self.config.base_frame, rclpy.time.Time()
            )
            translation = transform.transform.translation
            rotation = transform.transform.rotation
            position = np.asarray([translation.x, translation.y, translation.z], dtype=np.float64)
            quaternion = np.asarray(_validated_quaternion(rotation), dtype=np.float64)
            stamp = _stamp_seconds(transform.header)
            status.update({"tf_ok": True, "tf_stamp": stamp})
            if self._last_tf is not None:
                previous_position, previous_quaternion = self._last_tf
                status["tf_translation_jump_m"] = float(
                    np.linalg.norm(position - previous_position)
                )
                dot = float(np.clip(abs(np.dot(quaternion, previous_quaternion)), 0.0, 1.0))
                status["tf_rotation_jump_deg"] = float(np.degrees(2.0 * np.arccos(dot)))
            self._last_tf = position, quaternion
        except Exception as exc:
            status["tf_error"] = str(exc)
        self.visual_status.publish(status)


@dataclass(frozen=True)
class LocalizationHealth:
    healthy: bool
    reasons: tuple[str, ...]
    checked_at: float
    pose_age_s: float | None = None
    map_age_s: float | None = None
    tf_age_s: float | None = None
    inliers: int | None = None
    known_ratio: float | None = None
    free_ratio_of_known: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


class HELocalizationHealthConfig(ModuleConfig):
    evaluation_hz: float = Field(default=5.0, gt=0.0)
    max_pose_age_s: float = Field(default=0.5, gt=0.0)
    max_map_age_s: float = Field(default=3.0, gt=0.0)
    max_tf_age_s: float = Field(default=1.0, gt=0.0)
    min_inliers: int = Field(default=20, ge=1)
    min_known_ratio: float = Field(default=0.10, ge=0.0, le=1.0)
    min_free_ratio_of_known: float = Field(default=0.10, ge=0.0, le=1.0)
    max_tf_translation_jump_m: float = Field(default=0.5, gt=0.0)
    max_tf_rotation_jump_deg: float = Field(default=30.0, gt=0.0)
    max_latency_ms: float = Field(default=250.0, gt=0.0)
    max_slam_rss_mb: float = Field(default=768.0, gt=0.0)


class HELocalizationHealth(Module):
    """Evaluate visual localization inputs; missing or stale evidence is unhealthy."""

    config: HELocalizationHealthConfig
    visual_odom: In[Odometry]
    visual_map: In[OccupancyGrid]
    visual_status: In[dict]
    slam_runtime_status: In[dict]
    localization_health: Out[LocalizationHealth]

    def __init__(self, **config_args: Any) -> None:
        super().__init__(**config_args)
        self._odom: Odometry | None = None
        self._map: OccupancyGrid | None = None
        self._status: dict[str, Any] | None = None
        self._runtime_status: dict[str, Any] | None = None
        self._evaluation_task: asyncio.Task[None] | None = None

    async def main(self) -> AsyncGenerator[None, None]:
        self._evaluation_task = asyncio.create_task(self._evaluation_loop())
        try:
            yield
        finally:
            self._evaluation_task.cancel()
            try:
                await self._evaluation_task
            except asyncio.CancelledError:
                pass
            self._evaluation_task = None

    async def _evaluation_loop(self) -> None:
        while True:
            self.localization_health.publish(self.evaluate())
            await asyncio.sleep(1.0 / self.config.evaluation_hz)

    async def handle_visual_odom(self, msg: Odometry) -> None:
        self._odom = msg
        self.localization_health.publish(self.evaluate())

    async def handle_visual_map(self, msg: OccupancyGrid) -> None:
        self._map = msg
        self.localization_health.publish(self.evaluate())

    async def handle_visual_status(self, msg: dict) -> None:
        self._status = msg
        self.localization_health.publish(self.evaluate())

    async def handle_slam_runtime_status(self, msg: dict) -> None:
        self._runtime_status = msg
        self.localization_health.publish(self.evaluate())

    def evaluate(self, now: float | None = None) -> LocalizationHealth:
        now = time.time() if now is None else now
        reasons: list[str] = []
        pose_age = None if self._odom is None else max(0.0, now - self._odom.ts)
        map_age = None if self._map is None else max(0.0, now - self._map.ts)
        status = self._status or {}
        tf_stamp = status.get("tf_stamp")
        tf_age = None if tf_stamp is None else max(0.0, now - float(tf_stamp))

        if pose_age is None:
            reasons.append("pose_missing")
        elif pose_age > self.config.max_pose_age_s:
            reasons.append("pose_stale")
        if map_age is None:
            reasons.append("map_missing")
        elif map_age > self.config.max_map_age_s:
            reasons.append("map_stale")
        if not status:
            reasons.append("status_missing")
        if status.get("tracking_lost", True):
            reasons.append("tracking_lost")
        inliers = int(status.get("inliers", 0))
        if inliers < self.config.min_inliers:
            reasons.append("inliers_low")
        if not status.get("tf_ok", False):
            reasons.append("tf_unavailable")
        elif tf_age is None or tf_age > self.config.max_tf_age_s:
            reasons.append("tf_stale")
        if float(status.get("tf_translation_jump_m", 0.0)) > self.config.max_tf_translation_jump_m:
            reasons.append("tf_translation_jump")
        if float(status.get("tf_rotation_jump_deg", 0.0)) > self.config.max_tf_rotation_jump_deg:
            reasons.append("tf_rotation_jump")
        if float(status.get("odom_latency_ms", 0.0)) > self.config.max_latency_ms:
            reasons.append("slam_latency_high")

        runtime_status = self._runtime_status or {}
        if not runtime_status:
            reasons.append("runtime_status_missing")
        elif not runtime_status.get("process_alive", False):
            reasons.append("slam_process_down")
        if float(runtime_status.get("rss_mb", 0.0)) > self.config.max_slam_rss_mb:
            reasons.append("slam_memory_high")

        known_ratio = None
        free_ratio = None
        if self._map is not None and self._map.grid.size:
            known = int(np.count_nonzero(self._map.grid >= 0))
            free = int(np.count_nonzero(self._map.grid == 0))
            known_ratio = known / self._map.grid.size
            free_ratio = free / known if known else 0.0
            if known_ratio < self.config.min_known_ratio:
                reasons.append("map_known_ratio_low")
            if free_ratio < self.config.min_free_ratio_of_known:
                reasons.append("map_free_ratio_low")

        return LocalizationHealth(
            healthy=not reasons,
            reasons=tuple(dict.fromkeys(reasons)),
            checked_at=now,
            pose_age_s=pose_age,
            map_age_s=map_age,
            tf_age_s=tf_age,
            inliers=inliers,
            known_ratio=known_ratio,
            free_ratio_of_known=free_ratio,
            details={
                "tf_translation_jump_m": status.get("tf_translation_jump_m"),
                "tf_rotation_jump_deg": status.get("tf_rotation_jump_deg"),
                "odom_latency_ms": status.get("odom_latency_ms"),
                "slam_rss_mb": runtime_status.get("rss_mb"),
            },
        )


class HEVisualMapAdapterConfig(ModuleConfig):
    min_known_ratio: float = Field(default=0.10, ge=0.0, le=1.0)
    min_free_ratio_of_known: float = Field(default=0.10, ge=0.0, le=1.0)


class HEVisualMapAdapter(Module):
    """Expose only navigation-quality visual maps on DimOS global_costmap."""

    config: HEVisualMapAdapterConfig
    visual_map: In[OccupancyGrid]
    localization_health: In[LocalizationHealth]
    global_costmap: Out[OccupancyGrid]

    def __init__(self, **config_args: Any) -> None:
        super().__init__(**config_args)
        self._health: LocalizationHealth | None = None

    async def handle_localization_health(self, msg: LocalizationHealth) -> None:
        self._health = msg

    @staticmethod
    def quality(grid: OccupancyGrid) -> tuple[bool, dict[str, float]]:
        if grid.grid.ndim != 2 or grid.grid.size == 0 or grid.resolution <= 0.0:
            return False, {"known_ratio": 0.0, "free_ratio_of_known": 0.0}
        known = int(np.count_nonzero(grid.grid >= 0))
        free = int(np.count_nonzero(grid.grid == 0))
        return True, {
            "known_ratio": known / grid.grid.size,
            "free_ratio_of_known": free / known if known else 0.0,
        }

    async def handle_visual_map(self, msg: OccupancyGrid) -> None:
        structurally_valid, metrics = self.quality(msg)
        usable = (
            structurally_valid
            and self._health is not None
            and self._health.healthy
            and metrics["known_ratio"] >= self.config.min_known_ratio
            and metrics["free_ratio_of_known"] >= self.config.min_free_ratio_of_known
        )
        if usable:
            self.global_costmap.publish(msg.copy())
        else:
            logger.warning("Visual map withheld from planners: %s", metrics)


class HERTABMapShadowRunnerConfig(ModuleConfig):
    runner: str = ""


class HERTABMapShadowRunner(Module):
    """Own the native RTAB-Map shadow process group and clean it on shutdown."""

    dedicated_worker = True
    config: HERTABMapShadowRunnerConfig
    slam_runtime_status: Out[dict]

    def __init__(self, **config_args: Any) -> None:
        super().__init__(**config_args)
        self._process: subprocess.Popen[bytes] | None = None
        self._monitor_task: asyncio.Task[None] | None = None

    async def main(self) -> AsyncGenerator[None, None]:
        runner = self.config.runner or str(
            FilePath(__file__).parent / "deployment" / "run-he-rtabmap-shadow.sh"
        )
        self._process = subprocess.Popen(
            [runner], start_new_session=True, preexec_fn=_terminate_with_parent
        )
        self._monitor_task = asyncio.create_task(self._monitor())
        try:
            yield
        finally:
            if self._monitor_task is not None:
                self._monitor_task.cancel()
                try:
                    await self._monitor_task
                except asyncio.CancelledError:
                    pass
            self._stop_process_group()

    async def _monitor(self) -> None:
        while self._process is not None and self._process.poll() is None:
            self.slam_runtime_status.publish(
                {
                    "stamp": time.time(),
                    "process_alive": True,
                    "rss_mb": self._process_group_rss_mb(self._process.pid),
                }
            )
            await asyncio.sleep(1.0)
        if self._process is not None:
            self.slam_runtime_status.publish(
                {"stamp": time.time(), "process_alive": False, "rss_mb": 0.0}
            )
            logger.error("HE RTAB-Map shadow runner exited with %s", self._process.returncode)

    @staticmethod
    def _process_group_rss_mb(group_id: int) -> float:
        page_size = os.sysconf("SC_PAGE_SIZE")
        resident_pages = 0
        for entry in FilePath("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                fields = (entry / "stat").read_text().split()
                if int(fields[4]) != group_id:
                    continue
                resident_pages += int((entry / "statm").read_text().split()[1])
            except (FileNotFoundError, IndexError, PermissionError, ValueError):
                continue
        return resident_pages * page_size / (1024.0 * 1024.0)

    def _stop_process_group(self) -> None:
        process = self._process
        self._process = None
        if process is None or process.poll() is not None:
            return
        os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=7.0)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2.0)
