import json
from pathlib import Path

import pytest

from dimos.hardware.platforms.orin_nx.deployment.install import main, render_installation


def write_profile(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "platform": "test_robot",
                "ros": {
                    "distro_setup": "/opt/ros/humble/setup.bash",
                    "overlays": ["/opt/robot/install/setup.bash"],
                },
                "runtime": {"memory_high_mb": 768, "memory_max_mb": 1024},
            }
        )
    )


def test_render_uses_profile_and_has_no_home_hardcoding(tmp_path) -> None:
    profile = tmp_path / "profile.json"
    write_profile(profile)
    files = render_installation(
        repo=Path("/opt/dimos"),
        profile_path=profile,
        runtime_user="robot",
        python=Path("/opt/dimos/.venv/bin/python"),
        dimos_cli=Path("/opt/dimos/.venv/bin/dimos"),
        sense_blueprint="robot-sense",
        shadow_blueprint="robot-shadow",
    )

    sense = files[Path("etc/systemd/system/dimos-orin-sense.service")]
    environment = files[Path("etc/dimos/orin-nx.env")]
    assert "User=robot" in sense
    assert "MemoryHigh=768M" in sense
    assert "MemoryMax=1024M" in sense
    assert "/home/" not in "".join(files.values())
    assert 'DIMOS_SENSE_BLUEPRINT="robot-sense"' in environment
    assert 'DIMOS_ROS_OVERLAYS="/opt/robot/install/setup.bash"' in environment


def test_dry_run_validates_but_writes_nothing(tmp_path) -> None:
    profile = tmp_path / "profile.json"
    root = tmp_path / "root"
    write_profile(profile)

    result = main(
        [
            "--root",
            str(root),
            "--repo",
            "/opt/dimos",
            "--profile",
            str(profile),
            "--dry-run",
        ]
    )

    assert result == 0
    assert not root.exists()


def test_installer_defaults_to_generic_sense_blueprint(tmp_path) -> None:
    profile = tmp_path / "profile.json"
    root = tmp_path / "root"
    write_profile(profile)

    main(
        [
            "--root",
            str(root),
            "--repo",
            "/opt/dimos",
            "--profile",
            str(profile),
            "--no-systemctl",
        ]
    )

    environment = (root / "etc/dimos/orin-nx.env").read_text()
    assert 'DIMOS_SENSE_BLUEPRINT="orin-sense-headless"' in environment


def test_install_writes_units_without_enabling_services(tmp_path) -> None:
    profile = tmp_path / "profile.json"
    root = tmp_path / "root"
    write_profile(profile)

    result = main(
        [
            "--root",
            str(root),
            "--repo",
            "/opt/dimos",
            "--profile",
            str(profile),
            "--no-systemctl",
        ]
    )

    assert result == 0
    assert (root / "etc/dimos/orin-nx.env").is_file()
    assert (root / "etc/systemd/system/dimos-orin-storage-health.service").is_file()
    assert not (root / "etc/systemd/system/multi-user.target.wants").exists()


def test_rejects_invalid_runtime_user(tmp_path) -> None:
    profile = tmp_path / "profile.json"
    write_profile(profile)
    with pytest.raises(ValueError, match="invalid runtime user"):
        render_installation(
            repo=Path("/opt/dimos"),
            profile_path=profile,
            runtime_user="../../root",
            python=Path("/opt/dimos/.venv/bin/python"),
            dimos_cli=Path("/opt/dimos/.venv/bin/dimos"),
            sense_blueprint="",
            shadow_blueprint="",
        )
