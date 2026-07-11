"""Headless DimOS blueprints for the HE Ackermann platform."""

from __future__ import annotations

from dimos.core.coordination.blueprints import autoconnect
from dimos.navigation.movement_manager.movement_manager import MovementManager
from dimos.robot.he.connection import HEConnection
from dimos.robot.he.sensors import HESensorBridge
from dimos.robot.he.visual_slam import (
    HELocalizationHealth,
    HERTABMapShadowRunner,
    HEVisualMapAdapter,
    HEVisualSlamBridge,
)
from dimos.visualization.rerun.bridge import RerunBridgeModule
from dimos.visualization.rerun.websocket_server import RerunWebSocketServer

he_sense_headless = autoconnect(
    HESensorBridge.blueprint(),
    RerunBridgeModule.blueprint(
        rerun_open="none",
        memory_limit="128MB",
        latest_only_entities=[
            "world/color_image",
            "world/depth_image",
            "world/ir_image",
            "world/pointcloud",
            "world/camera_info",
            "world/depth_camera_info",
            "world/odom",
            "world/imu",
        ],
    ),
).global_config(n_workers=2)


he_teleop_headless = autoconnect(
    HESensorBridge.blueprint(),
    MovementManager.blueprint(),
    HEConnection.blueprint(enabled=False),
    RerunBridgeModule.blueprint(
        rerun_open="none",
        memory_limit="256MB",
        latest_only_entities=[
            "world/color_image",
            "world/depth_image",
            "world/ir_image",
            "world/pointcloud",
            "world/camera_info",
            "world/depth_camera_info",
            "world/odom",
            "world/imu",
        ],
    ),
    RerunWebSocketServer.blueprint(),
).global_config(n_workers=3)


he_visual_slam_shadow = autoconnect(
    HESensorBridge.blueprint(),
    RerunBridgeModule.blueprint(
        rerun_open="none",
        memory_limit="256MB",
        latest_only_entities=[
            "world/color_image",
            "world/depth_image",
            "world/ir_image",
            "world/pointcloud",
            "world/camera_info",
            "world/depth_camera_info",
            "world/odom",
            "world/imu",
            "world/visual_odom",
            "world/visual_map",
            "world/visual_path",
            "world/visual_status",
            "world/localization_health",
            "world/global_costmap",
        ],
    ),
    HEVisualMapAdapter.blueprint(),
    HELocalizationHealth.blueprint(),
    HEVisualSlamBridge.blueprint(),
    HERTABMapShadowRunner.blueprint(),
).global_config(n_workers=4)
