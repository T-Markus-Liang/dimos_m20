"""Headless DimOS blueprints for the HE Ackermann platform."""

from __future__ import annotations

from dimos.core.coordination.blueprints import autoconnect
from dimos.navigation.movement_manager.movement_manager import MovementManager
from dimos.visualization.rerun.bridge import RerunBridgeModule
from dimos.visualization.rerun.websocket_server import RerunWebSocketServer

from dimos.robot.he.connection import HEConnection
from dimos.robot.he.sensors import HESensorBridge


he_sense_headless = autoconnect(
    HESensorBridge.blueprint(),
    RerunBridgeModule.blueprint(
        rerun_open="none",
        memory_limit="256MB",
        latest_only_entities=[
            "world/lidar",
            "world/odom",
            "world/imu",
            "world/camera_pointcloud",
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
            "world/lidar",
            "world/odom",
            "world/imu",
            "world/camera_pointcloud",
        ],
    ),
    RerunWebSocketServer.blueprint(),
).global_config(n_workers=3)
