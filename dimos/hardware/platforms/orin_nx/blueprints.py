"""Profile-driven, read-only sensor blueprint for Orin NX deployments."""

from __future__ import annotations

import os
from pathlib import Path

from dimos.core.coordination.blueprints import Blueprint, autoconnect
from dimos.hardware.platforms.profile import PlatformProfile
from dimos.hardware.sensors.ros2_bridge import ROS2SensorBridge
from dimos.visualization.rerun.bridge import RerunBridgeModule

PROFILE_ENV = "DIMOS_PROFILE"
_DEFAULT_PROFILE = Path(__file__).with_name("sense_profile.json")
_LATEST_SENSOR_ENTITIES = [
    "world/color_image",
    "world/depth_image",
    "world/depth_quality",
    "world/ir_image",
    "world/pointcloud",
    "world/camera_info",
    "world/depth_camera_info",
    "world/odom",
    "world/imu",
]


def load_sense_profile(path: str | Path | None = None) -> PlatformProfile:
    selected = Path(path or os.environ.get(PROFILE_ENV, _DEFAULT_PROFILE))
    return PlatformProfile.from_json(selected)


def build_sense_blueprint(profile: PlatformProfile) -> Blueprint:
    return autoconnect(
        ROS2SensorBridge.blueprint(**profile.sensor_config()),
        RerunBridgeModule.blueprint(
            rerun_open="none",
            memory_limit=profile.runtime.rerun_memory,
            latest_only_entities=_LATEST_SENSOR_ENTITIES,
        ),
    ).global_config(n_workers=profile.runtime.workers)


_sense_profile = load_sense_profile()


def _sense_requirements() -> str | None:
    if PROFILE_ENV not in os.environ:
        return f"{PROFILE_ENV} must point to a validated robot profile"
    if _sense_profile.control.enabled:
        return "orin-sense-headless rejects profiles with motion output enabled"
    if not any(
        stream.enabled
        for name, stream in _sense_profile.sensors
        if name != "pointcloud_stride"
    ):
        return "orin-sense-headless requires at least one enabled sensor stream"
    return None


orin_sense_headless = build_sense_blueprint(_sense_profile).requirements(_sense_requirements)
