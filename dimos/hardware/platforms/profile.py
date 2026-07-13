"""Validated robot profile shared by compute-platform deployments."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ROSProfile(StrictModel):
    distro_setup: str = "/opt/ros/humble/setup.bash"
    overlays: list[str] = Field(default_factory=list)


class SensorStreamProfile(StrictModel):
    enabled: bool = False
    topic: str = ""
    max_hz: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_enabled_stream(self) -> SensorStreamProfile:
        if self.enabled and (not self.topic.startswith("/") or self.max_hz <= 0.0):
            raise ValueError("enabled sensor streams require an absolute topic and max_hz > 0")
        return self


class SensorsProfile(StrictModel):
    odom: SensorStreamProfile = Field(default_factory=SensorStreamProfile)
    imu: SensorStreamProfile = Field(default_factory=SensorStreamProfile)
    color: SensorStreamProfile = Field(default_factory=SensorStreamProfile)
    depth: SensorStreamProfile = Field(default_factory=SensorStreamProfile)
    ir: SensorStreamProfile = Field(default_factory=SensorStreamProfile)
    points: SensorStreamProfile = Field(default_factory=SensorStreamProfile)
    camera_info: SensorStreamProfile = Field(default_factory=SensorStreamProfile)
    depth_camera_info: SensorStreamProfile = Field(default_factory=SensorStreamProfile)
    pointcloud_stride: int = Field(default=8, ge=1)

    @model_validator(mode="after")
    def reject_duplicate_topics(self) -> SensorsProfile:
        enabled = [
            stream.topic
            for name, stream in self
            if name != "pointcloud_stride" and isinstance(stream, SensorStreamProfile) and stream.enabled
        ]
        if len(enabled) != len(set(enabled)):
            raise ValueError("enabled sensor topics must be unique")
        return self


class ControlProfile(StrictModel):
    backend: Literal["none", "ros2_twist", "custom"] = "none"
    enabled: bool = False
    topic: str = ""
    allow_lateral: bool = False
    max_linear_mps: float = Field(default=0.10, gt=0.0)
    max_lateral_mps: float = Field(default=0.0, ge=0.0)
    max_angular_radps: float = Field(default=0.30, gt=0.0)
    rate_hz: float = Field(default=20.0, gt=0.0)
    timeout_s: float = Field(default=0.20, gt=0.0)

    @model_validator(mode="after")
    def validate_control(self) -> ControlProfile:
        if self.enabled and self.backend == "none":
            raise ValueError("enabled control requires a backend")
        if self.backend == "ros2_twist" and not self.topic.startswith("/"):
            raise ValueError("ros2_twist requires an absolute output topic")
        if not self.allow_lateral and self.max_lateral_mps != 0.0:
            raise ValueError("max_lateral_mps must be zero when lateral motion is disabled")
        if self.allow_lateral and self.max_lateral_mps <= 0.0:
            raise ValueError("lateral motion requires max_lateral_mps > 0")
        return self


class RuntimeProfile(StrictModel):
    rerun_memory: str = "128MB"
    workers: int = Field(default=2, ge=1)
    memory_high_mb: int = Field(default=1024, ge=128)
    memory_max_mb: int = Field(default=1280, ge=128)

    @model_validator(mode="after")
    def validate_memory(self) -> RuntimeProfile:
        if self.memory_high_mb > self.memory_max_mb:
            raise ValueError("memory_high_mb cannot exceed memory_max_mb")
        return self


class PlatformProfile(StrictModel):
    platform: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    ros: ROSProfile = Field(default_factory=ROSProfile)
    sensors: SensorsProfile = Field(default_factory=SensorsProfile)
    control: ControlProfile = Field(default_factory=ControlProfile)
    runtime: RuntimeProfile = Field(default_factory=RuntimeProfile)

    @classmethod
    def from_json(cls, path: str | Path) -> PlatformProfile:
        return cls.model_validate(json.loads(Path(path).read_text()))

    def sensor_config(self) -> dict[str, object]:
        sensors = self.sensors
        return {
            "enable_odom": sensors.odom.enabled,
            "odom_topic": sensors.odom.topic,
            "odom_max_hz": sensors.odom.max_hz,
            "enable_imu": sensors.imu.enabled,
            "imu_topic": sensors.imu.topic,
            "imu_max_hz": sensors.imu.max_hz,
            "enable_color_image": sensors.color.enabled,
            "color_image_topic": sensors.color.topic,
            "color_image_max_hz": sensors.color.max_hz,
            "enable_depth_image": sensors.depth.enabled,
            "depth_image_topic": sensors.depth.topic,
            "depth_image_max_hz": sensors.depth.max_hz,
            "enable_ir_image": sensors.ir.enabled,
            "ir_image_topic": sensors.ir.topic,
            "ir_image_max_hz": sensors.ir.max_hz,
            "enable_pointcloud": sensors.points.enabled,
            "pointcloud_topic": sensors.points.topic,
            "pointcloud_max_hz": sensors.points.max_hz,
            "enable_camera_info": sensors.camera_info.enabled,
            "camera_info_topic": sensors.camera_info.topic,
            "camera_info_max_hz": sensors.camera_info.max_hz,
            "enable_depth_camera_info": sensors.depth_camera_info.enabled,
            "depth_camera_info_topic": sensors.depth_camera_info.topic,
            "depth_camera_info_max_hz": sensors.depth_camera_info.max_hz,
            "pointcloud_stride": sensors.pointcloud_stride,
        }

    def ros2_twist_config(self) -> dict[str, object]:
        control = self.control
        if control.backend not in ("none", "ros2_twist"):
            raise ValueError(f"profile uses non-ROS control backend {control.backend!r}")
        return {
            "enabled": control.enabled,
            "ros_cmd_vel_topic": control.topic,
            "allow_lateral": control.allow_lateral,
            "max_linear_mps": control.max_linear_mps,
            "max_lateral_mps": control.max_lateral_mps,
            "max_angular_radps": control.max_angular_radps,
            "cmd_rate_hz": control.rate_hz,
            "cmd_timeout_s": control.timeout_s,
        }
