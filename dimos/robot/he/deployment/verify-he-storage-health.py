#!/usr/bin/env python3
"""Gate HE runtime startup on current NVMe and kernel storage health."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time

from dimos.robot.he.storage_health import summarize_storage_health


def command(*args: str) -> str:
    result = subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        timeout=15.0,
    )
    return result.stdout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="/dev/nvme0")
    parser.add_argument("--smart-input", type=Path)
    parser.add_argument("--kernel-input", type=Path)
    parser.add_argument("--output", type=Path, default=Path("/run/he-storage-health.json"))
    args = parser.parse_args()

    smart_text = (
        args.smart_input.read_text(encoding="utf-8")
        if args.smart_input
        else command("nvme", "smart-log", args.device)
    )
    kernel_text = (
        args.kernel_input.read_text(encoding="utf-8")
        if args.kernel_input
        else command("dmesg", "--ctime")
    )
    report = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "device": args.device,
        "summary": summarize_storage_health(smart_text, kernel_text),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    if not report["summary"]["healthy"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
