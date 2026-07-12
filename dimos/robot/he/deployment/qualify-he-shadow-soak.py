#!/usr/bin/env python3
"""Collect a bounded, payload-free HE shadow resource soak."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any

from dimos.robot.he.memory_data import parse_kb_fields, parse_memory_stat
from dimos.robot.he.shadow_soak import (
    is_volatile_output,
    parse_tegrastats,
    summarize_shadow_soak,
)


def command(*args: str, timeout: float = 10.0) -> str:
    result = subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout


def systemd_properties(service: str) -> dict[str, str]:
    names = (
        "ActiveState",
        "ControlGroup",
        "CPUUsageNSec",
        "MemoryCurrent",
        "MemoryMax",
        "NRestarts",
        "TasksCurrent",
    )
    args = ["systemctl", "show", service]
    for name in names:
        args.extend(("--property", name))
    return dict(
        line.split("=", 1) for line in command(*args).splitlines() if "=" in line
    )


def tegrastats() -> dict[str, float]:
    result = subprocess.run(
        ["timeout", "2", "tegrastats", "--interval", "1000"],
        check=False,
        capture_output=True,
        text=True,
        timeout=4.0,
    )
    parsed = parse_tegrastats(result.stdout)
    if parsed is None:
        raise RuntimeError("tegrastats produced no parseable sample")
    return parsed


def nav_publishers() -> int:
    output = command("ros2", "topic", "info", "/he/nav_cmd_vel", "-v", timeout=15.0)
    match = re.search(r"^Publisher count:\s*(\d+)$", output, re.MULTILINE)
    if not match:
        raise RuntimeError("nav publisher count is unavailable")
    return int(match.group(1))


def integer_property(properties: dict[str, str], name: str, errors: list[str]) -> int:
    try:
        return int(properties[name])
    except (KeyError, ValueError):
        errors.append(f"systemd property is unavailable: {name}")
        return -1


def collect_sample(service: str, started: float) -> dict[str, Any]:
    properties = systemd_properties(service)
    cgroup = Path("/sys/fs/cgroup" + properties["ControlGroup"])
    memory = parse_kb_fields(Path("/proc/meminfo").read_text())
    swap_used = memory["SwapTotal"] - memory["SwapFree"]
    errors: list[str] = []
    try:
        memory_events = parse_memory_stat((cgroup / "memory.events").read_text())
    except OSError as exc:
        memory_events = {}
        errors.append(f"cgroup memory events are unavailable: {exc}")
    try:
        gpu = tegrastats()
    except (RuntimeError, subprocess.SubprocessError) as exc:
        gpu = {"gpu_percent": 0.0, "max_temperature_c": 0.0}
        errors.append(str(exc))
    try:
        publishers = nav_publishers()
    except (RuntimeError, subprocess.SubprocessError) as exc:
        publishers = -1
        errors.append(str(exc))
    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_seconds": time.monotonic() - started,
        "service_state": properties["ActiveState"],
        "restart_count": integer_property(properties, "NRestarts", errors),
        "memory_current_bytes": integer_property(properties, "MemoryCurrent", errors),
        "memory_max_bytes": integer_property(properties, "MemoryMax", errors),
        "tasks_current": integer_property(properties, "TasksCurrent", errors),
        "cpu_usage_nsec": integer_property(properties, "CPUUsageNSec", errors),
        "memory_events": memory_events,
        "available_memory_bytes": memory["MemAvailable"],
        "swap_used_bytes": swap_used,
        "nav_cmd_vel_publishers": publishers,
        "tegrastats": gpu,
        "errors": errors,
    }


def write_report(
    output: Path,
    service: str,
    requested_duration: float,
    interval: float,
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    report = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "service": service,
        "requested_duration_seconds": requested_duration,
        "sample_interval_seconds": interval,
        "summary": summarize_shadow_soak(samples),
        "samples": samples,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(rendered, encoding="utf-8")
    temporary.replace(output)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", default="he-dimos-shadow.service")
    parser.add_argument("--duration", type=float, default=3600.0)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 60.0 <= args.duration <= 14400.0:
        parser.error("--duration must be between 60 and 14400 seconds")
    if not 5.0 <= args.interval <= 300.0:
        parser.error("--interval must be between 5 and 300 seconds")
    if is_volatile_output(args.output):
        parser.error("--output must use persistent storage, not /tmp, /run, or /dev/shm")

    samples: list[dict[str, Any]] = []
    started = time.monotonic()
    next_sample = started
    try:
        while True:
            time.sleep(max(0.0, next_sample - time.monotonic()))
            samples.append(collect_sample(args.service, started))
            report = write_report(
                args.output, args.service, args.duration, args.interval, samples
            )
            if samples[-1]["elapsed_seconds"] >= args.duration:
                break
            next_sample = min(next_sample + args.interval, started + args.duration)
    except KeyboardInterrupt:
        report = write_report(args.output, args.service, args.duration, args.interval, samples)
        raise SystemExit(130) from None

    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    if not report["summary"]["accepted"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
