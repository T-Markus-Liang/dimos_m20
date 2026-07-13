import json

from dimos.hardware.drive_trains.ros2_twist import ROS2TwistConnection
import dimos.hardware.platforms.orin_nx.blueprints as sense_blueprints
from dimos.hardware.platforms.orin_nx.blueprints import (
    build_sense_blueprint,
    load_sense_profile,
)
from dimos.hardware.sensors.ros2_bridge import ROS2SensorBridge
from dimos.visualization.rerun.bridge import RerunBridgeModule


def test_profile_drives_read_only_sense_blueprint(tmp_path) -> None:
    path = tmp_path / "profile.json"
    path.write_text(
        json.dumps(
            {
                "platform": "test_robot",
                "sensors": {
                    "imu": {"enabled": True, "topic": "/imu", "max_hz": 20}
                },
                "runtime": {
                    "rerun_memory": "96MB",
                    "workers": 2,
                    "memory_high_mb": 512,
                    "memory_max_mb": 768,
                },
            }
        )
    )
    profile = load_sense_profile(path)

    blueprint = build_sense_blueprint(profile)
    atoms = {atom.module: atom for atom in blueprint.blueprints}

    assert set(atoms) == {ROS2SensorBridge, RerunBridgeModule}
    assert ROS2TwistConnection not in atoms
    assert atoms[ROS2SensorBridge].kwargs["enable_imu"] is True
    assert atoms[ROS2SensorBridge].kwargs["imu_topic"] == "/imu"
    assert atoms[RerunBridgeModule].kwargs["rerun_open"] == "none"
    assert atoms[RerunBridgeModule].kwargs["memory_limit"] == "96MB"
    assert blueprint.global_config_overrides["n_workers"] == 2


def test_repository_default_profile_is_inert(monkeypatch) -> None:
    monkeypatch.delenv("DIMOS_PROFILE", raising=False)
    profile = load_sense_profile()
    assert profile.platform == "orin_nx_unconfigured"
    assert profile.control.enabled is False
    assert not any(
        stream.enabled
        for name, stream in profile.sensors
        if name != "pointcloud_stride"
    )


def test_requirements_reject_missing_profile_environment(monkeypatch) -> None:
    monkeypatch.delenv("DIMOS_PROFILE", raising=False)
    assert sense_blueprints._sense_requirements() == (
        "DIMOS_PROFILE must point to a validated robot profile"
    )


def test_requirements_reject_inert_or_motion_enabled_profile(monkeypatch) -> None:
    monkeypatch.setenv("DIMOS_PROFILE", "/tmp/profile.json")
    inert = load_sense_profile(
        sense_blueprints._DEFAULT_PROFILE  # type: ignore[attr-defined]
    )
    monkeypatch.setattr(sense_blueprints, "_sense_profile", inert)
    assert sense_blueprints._sense_requirements() == (
        "orin-sense-headless requires at least one enabled sensor stream"
    )

    motion = inert.model_copy(
        update={
            "control": inert.control.model_copy(
                update={
                    "backend": "ros2_twist",
                    "enabled": True,
                    "topic": "/cmd_vel",
                }
            )
        }
    )
    monkeypatch.setattr(sense_blueprints, "_sense_profile", motion)
    assert sense_blueprints._sense_requirements() == (
        "orin-sense-headless rejects profiles with motion output enabled"
    )
