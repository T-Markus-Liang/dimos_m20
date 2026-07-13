"""Render portable Orin NX systemd units without enabling runtime services."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess

from dimos.hardware.platforms.profile import PlatformProfile

_UNIT_NAMES = (
    "dimos-orin-storage-health.service",
    "dimos-orin-sense.service",
    "dimos-orin-shadow.service",
)
_USER = re.compile(r"^[a-z_][a-z0-9_-]*[$]?$")


def _environment_value(value: str) -> str:
    if "\n" in value or "\r" in value:
        raise ValueError("environment values cannot contain newlines")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_installation(
    *,
    repo: Path,
    profile_path: Path,
    runtime_user: str,
    python: Path,
    dimos_cli: Path,
    sense_blueprint: str,
    shadow_blueprint: str,
) -> dict[Path, str]:
    if not _USER.fullmatch(runtime_user):
        raise ValueError(f"invalid runtime user: {runtime_user!r}")
    profile = PlatformProfile.from_json(profile_path)
    deployment = Path(__file__).parent
    runner = (
        repo
        / "dimos"
        / "hardware"
        / "platforms"
        / "orin_nx"
        / "deployment"
        / "run-blueprint.sh"
    )
    replacements = {
        "@DIMOS_REPO@": str(repo),
        "@DIMOS_PYTHON@": str(python),
        "@DIMOS_RUNTIME_USER@": runtime_user,
        "@DIMOS_RUNNER@": str(runner),
        "@MEMORY_HIGH_MB@": str(profile.runtime.memory_high_mb),
        "@MEMORY_MAX_MB@": str(profile.runtime.memory_max_mb),
    }
    rendered: dict[Path, str] = {}
    for unit_name in _UNIT_NAMES:
        content = (deployment / f"{unit_name}.in").read_text(encoding="utf-8")
        for token, value in replacements.items():
            content = content.replace(token, value)
        if "@" in content:
            raise ValueError(f"unresolved template token in {unit_name}")
        rendered[Path("etc/systemd/system") / unit_name] = content

    environment = {
        "DIMOS_REPO": str(repo),
        "DIMOS_PYTHON": str(python),
        "DIMOS_CLI": str(dimos_cli),
        "DIMOS_PROFILE": str(profile_path),
        "DIMOS_ROS_SETUP": profile.ros.distro_setup,
        "DIMOS_ROS_OVERLAYS": ":".join(profile.ros.overlays),
        "DIMOS_SENSE_BLUEPRINT": sense_blueprint,
        "DIMOS_SHADOW_BLUEPRINT": shadow_blueprint,
        "DIMOS_NVME_DEVICE": "/dev/nvme0",
        "DIMOS_STORAGE_REPORT": "/run/dimos/orin-nx-storage-health.json",
    }
    rendered[Path("etc/dimos/orin-nx.env")] = "".join(
        f"{key}={_environment_value(value)}\n" for key, value in environment.items()
    )
    return rendered


def install_files(root: Path, files: dict[Path, str], *, dry_run: bool) -> None:
    for relative, content in files.items():
        destination = root / relative
        print(f"{'would write' if dry_run else 'write'} {destination}")
        if dry_run:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f".{destination.name}.tmp")
        temporary.write_text(content, encoding="utf-8")
        temporary.chmod(0o644)
        temporary.replace(destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("/"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--runtime-user", default="dimos")
    parser.add_argument("--python", type=Path)
    parser.add_argument("--dimos-cli", type=Path)
    parser.add_argument("--sense-blueprint", default="orin-sense-headless")
    parser.add_argument("--shadow-blueprint", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-systemctl", action="store_true")
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    profile = args.profile.resolve()
    files = render_installation(
        repo=repo,
        profile_path=profile,
        runtime_user=args.runtime_user,
        python=(args.python or repo / ".venv/bin/python").resolve(),
        dimos_cli=(args.dimos_cli or repo / ".venv/bin/dimos").resolve(),
        sense_blueprint=args.sense_blueprint,
        shadow_blueprint=args.shadow_blueprint,
    )
    install_files(args.root.resolve(), files, dry_run=args.dry_run)
    if not args.dry_run and not args.no_systemctl and args.root.resolve() == Path("/"):
        subprocess.run(["systemctl", "daemon-reload"], check=True)
    print("No DimOS runtime service was enabled or started.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
