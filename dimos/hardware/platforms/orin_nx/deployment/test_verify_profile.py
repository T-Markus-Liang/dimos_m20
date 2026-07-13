import json

from dimos.hardware.platforms.orin_nx.deployment.verify_profile import main


def test_accepts_read_only_profile(tmp_path) -> None:
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"platform": "robot"}))
    assert main(["--profile", str(profile)]) == 0


def test_rejects_motion_enabled_profile_by_default(tmp_path) -> None:
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps(
            {
                "platform": "robot",
                "control": {
                    "backend": "ros2_twist",
                    "enabled": True,
                    "topic": "/cmd_vel",
                },
            }
        )
    )
    assert main(["--profile", str(profile)]) == 1
    assert main(["--profile", str(profile), "--allow-motion"]) == 0
