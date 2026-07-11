#!/usr/bin/env python3
"""Capture one bounded systemd-cgroup and process memory snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time
from typing import Any

from dimos.robot.he.memory_data import (
    parse_anonymous_mappings,
    parse_kb_fields,
    parse_memory_stat,
)


def systemd_properties(service: str) -> dict[str, str]:
    names = (
        "ControlGroup",
        "MainPID",
        "MemoryCurrent",
        "MemoryHigh",
        "MemoryMax",
        "NRestarts",
    )
    command = ["systemctl", "show", service]
    for name in names:
        command.extend(("--property", name))
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=10.0,
    )
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def process_role(pid: int, ppid: int, main_pid: int, command: str) -> str:
    if pid == main_pid:
        return "coordinator"
    if "resource_tracker" in command:
        return "resource_tracker"
    if "watchdog_main" in command:
        return "watchdog"
    if ppid == main_pid and "forkserver" in command:
        return "forkserver"
    if "forkserver" in command:
        return "worker"
    return "child"


def read_process(pid: int, main_pid: int) -> dict[str, Any]:
    root = Path("/proc") / str(pid)
    status = dict(
        line.split(":", 1) for line in (root / "status").read_text().splitlines() if ":" in line
    )
    ppid = int(status["PPid"].strip())
    command = (root / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
    rollup = parse_kb_fields((root / "smaps_rollup").read_text())
    mappings = parse_anonymous_mappings((root / "smaps").read_text())[:10]
    return {
        "pid": pid,
        "ppid": ppid,
        "role": process_role(pid, ppid, main_pid, command),
        "command": command,
        "threads": int(status["Threads"].strip()),
        "fd_count": len(list((root / "fd").iterdir())),
        "memory": rollup,
        "largest_anonymous_mappings": mappings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--service", default="he-dimos-sense.service")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    properties = systemd_properties(args.service)
    main_pid = int(properties["MainPID"])
    cgroup = Path("/sys/fs/cgroup" + properties["ControlGroup"])
    processes = []
    skipped = []
    for pid in sorted(int(item) for item in (cgroup / "cgroup.procs").read_text().split()):
        try:
            processes.append(read_process(pid, main_pid))
        except (FileNotFoundError, ProcessLookupError):
            skipped.append(pid)

    report = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "service": args.service,
        "systemd": properties,
        "cgroup": {
            "memory_current_bytes": int((cgroup / "memory.current").read_text()),
            "memory_stat": parse_memory_stat((cgroup / "memory.stat").read_text()),
        },
        "processes": processes,
        "skipped_processes": skipped,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
