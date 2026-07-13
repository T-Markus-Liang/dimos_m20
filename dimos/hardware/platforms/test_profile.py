import json
from pathlib import Path

from pydantic import ValidationError
import pytest

from dimos.hardware.drive_trains.ros2_twist import ROS2TwistConnectionConfig
from dimos.hardware.platforms.profile import PlatformProfile
from dimos.hardware.sensors.ros2_bridge import ROS2SensorBridgeConfig


def profile_data() -> dict:
    return {
        "platform": "test_robot",
        "sensors": {
            "imu": {"enabled": True, "topic": "/imu", "max_hz": 20},
            "color": {"enabled": True, "topic": "/camera/image", "max_hz": 5},
        },
        "control": {"backend": "ros2_twist", "topic": "/nav_cmd_vel"},
    }


def test_profile_load_and_module_configs(tmp_path) -> None:
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile_data()))

    profile = PlatformProfile.from_json(path)

    assert profile.sensor_config()["imu_topic"] == "/imu"
    assert profile.sensor_config()["enable_depth_image"] is False
    assert profile.ros2_twist_config()["enabled"] is False


def test_he_reference_profile_constructs_generic_module_configs() -> None:
    profile_path = Path(__file__).parents[2] / "robot" / "he" / "profile.json"
    profile = PlatformProfile.from_json(profile_path)

    sensor_config = ROS2SensorBridgeConfig(**profile.sensor_config())
    control_config = ROS2TwistConnectionConfig(**profile.ros2_twist_config())

    assert sensor_config.enable_color_image is True
    assert sensor_config.enable_pointcloud is True
    assert control_config.enabled is False


@pytest.mark.parametrize(
    "update",
    [
        lambda data: data["sensors"].update(
            {"depth": {"enabled": True, "topic": "relative", "max_hz": 5}}
        ),
        lambda data: data["sensors"].update(
            {"depth": {"enabled": True, "topic": "/imu", "max_hz": 5}}
        ),
        lambda data: data["control"].update({"enabled": True, "backend": "none"}),
        lambda data: data["control"].update({"max_lateral_mps": 0.1}),
        lambda data: data.update({"unknown": True}),
    ],
)
def test_profile_rejects_unsafe_or_unknown_values(update) -> None:
    data = profile_data()
    update(data)

    with pytest.raises(ValidationError):
        PlatformProfile.model_validate(data)
