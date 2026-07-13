"""Read-only Jetson compatibility report for Orin NX deployments."""

from __future__ import annotations

import argparse
from importlib import metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import time
from typing import Any

_L4T_RELEASE = re.compile(r"R(?P<major>\d+).*?REVISION:\s*(?P<revision>[\d.]+)", re.I)
_PACKAGE_VERSION = re.compile(r"(?P<version>\d+\.\d+(?:\.\d+)?)")
_CUDA_RELEASE = re.compile(r"(?:release|CUDA Version)\s*[: ]\s*(?P<version>\d+\.\d+)", re.I)
_TARGET_L4T_PREFIX = "36.4."
_TARGET_UBUNTU = "22.04"
_TARGET_CUDA_PREFIX = "12.6"
_ML_WHEEL_PYTHON = (3, 10)


def parse_l4t_version(tegra_release: str, package_version: str = "") -> str | None:
    match = _L4T_RELEASE.search(tegra_release)
    if match:
        return f"{match.group('major')}.{match.group('revision')}"
    match = _PACKAGE_VERSION.search(package_version)
    return match.group("version") if match else None


def parse_cuda_version(text: str) -> str | None:
    match = _CUDA_RELEASE.search(text)
    if match:
        return match.group("version")
    try:
        value = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    cuda = value.get("cuda", {}) if isinstance(value, dict) else {}
    version = cuda.get("version") if isinstance(cuda, dict) else None
    return str(version) if version else None


def parse_os_release(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, value = line.split("=", 1)
        values[key] = value.strip().strip('"')
    return values


def _read(path: str | Path) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _command(*args: str) -> str:
    try:
        result = subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
            timeout=10.0,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip()


def _memory_total_mb(meminfo: str) -> int | None:
    match = re.search(r"^MemTotal:\s+(\d+)\s+kB$", meminfo, re.M)
    return round(int(match.group(1)) / 1024) if match else None


def _installed_version(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def collect_compatibility_report() -> dict[str, Any]:
    os_release = parse_os_release(_read("/etc/os-release"))
    tegra_release = _read("/etc/nv_tegra_release")
    l4t_package = _command("dpkg-query", "-W", "-f=${Version}", "nvidia-l4t-core")
    cuda_text = _command("nvcc", "--version") or _read("/usr/local/cuda/version.json")
    model = _read("/proc/device-tree/model").rstrip("\x00")
    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "system": platform.system(),
        "architecture": platform.machine(),
        "ubuntu_version": os_release.get("VERSION_ID"),
        "jetson_model": model or None,
        "l4t_version": parse_l4t_version(tegra_release, l4t_package),
        "cuda_version": parse_cuda_version(cuda_text),
        "python_version": platform.python_version(),
        "memory_total_mb": _memory_total_mb(_read("/proc/meminfo")),
        "packages": {
            name: _installed_version(name)
            for name in (
                "open3d-unofficial-arm",
                "onnxruntime-gpu",
                "torch",
                "torchvision",
                "xformers",
            )
        },
    }


def assess_compatibility(report: dict[str, Any]) -> dict[str, list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if report.get("system") != "Linux":
        errors.append("target_requires_linux")
    if report.get("architecture") != "aarch64":
        errors.append("target_requires_aarch64")

    l4t = report.get("l4t_version")
    if not l4t:
        errors.append("l4t_not_detected")
    elif not str(l4t).startswith(_TARGET_L4T_PREFIX):
        errors.append(f"unqualified_l4t:{l4t}")

    ubuntu = report.get("ubuntu_version")
    if ubuntu != _TARGET_UBUNTU:
        errors.append(f"unqualified_ubuntu:{ubuntu or 'unknown'}")

    python_text = str(report.get("python_version") or "")
    try:
        python_version = tuple(int(part) for part in python_text.split(".")[:2])
    except ValueError:
        python_version = (0, 0)
    if not (python_version >= (3, 10) and python_version < (3, 13)):
        errors.append(f"unsupported_python:{python_text or 'unknown'}")
    elif python_version != _ML_WHEEL_PYTHON:
        warnings.append(f"jetson_ml_wheels_are_qualified_for_cp310:not_{python_text}")

    cuda = report.get("cuda_version")
    if not cuda:
        warnings.append("cuda_not_detected")
    elif not str(cuda).startswith(_TARGET_CUDA_PREFIX):
        warnings.append(f"unqualified_cuda:{cuda}")

    memory = report.get("memory_total_mb")
    if isinstance(memory, int) and memory < 7000:
        warnings.append(f"less_than_8gb_class_memory:{memory}mb")
    return {"errors": errors, "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Return nonzero for warnings as well as compatibility errors.",
    )
    args = parser.parse_args(argv)

    report = collect_compatibility_report()
    report["assessment"] = assess_compatibility(report)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    errors = report["assessment"]["errors"]
    warnings = report["assessment"]["warnings"]
    return 1 if errors or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
