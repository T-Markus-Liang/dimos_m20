"""Fail-closed NVMe and kernel storage admission for Orin deployments."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any

_KERNEL_FAILURE = re.compile(
    r"critical medium error|EXT4-fs error|I/O error.*nvme|blk_update_request.*error",
    re.IGNORECASE,
)
_WANTED_SMART_FIELDS = {
    "critical_warning",
    "available_spare",
    "available_spare_threshold",
    "media_errors",
    "unsafe_shutdowns",
}


def _integer(value: str) -> int:
    return int(value.strip().rstrip("%").replace(",", ""), 0)


def parse_nvme_smart(text: str) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        name = name.strip()
        if name in _WANTED_SMART_FIELDS:
            values[name] = _integer(value.split()[0])
    missing = sorted(_WANTED_SMART_FIELDS - values.keys())
    if missing:
        raise ValueError(f"missing NVMe SMART fields: {', '.join(missing)}")
    return values


def summarize_storage_health(smart_text: str, kernel_text: str) -> dict[str, Any]:
    smart = parse_nvme_smart(smart_text)
    kernel_errors = [
        line.strip() for line in kernel_text.splitlines() if _KERNEL_FAILURE.search(line)
    ]
    reasons: list[str] = []
    if smart["critical_warning"] != 0:
        reasons.append("nvme_critical_warning")
    if smart["media_errors"] != 0:
        reasons.append("nvme_media_errors")
    if smart["available_spare"] < smart["available_spare_threshold"]:
        reasons.append("nvme_spare_below_threshold")
    if kernel_errors:
        reasons.append("kernel_storage_errors")
    return {
        "healthy": not reasons,
        "reasons": reasons,
        "smart": smart,
        "kernel_error_count": len(kernel_errors),
        "kernel_errors": kernel_errors[:50],
    }


def _command(*args: str) -> str:
    result = subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        timeout=15.0,
    )
    return result.stdout


def build_report(
    device: str,
    *,
    smart_input: Path | None = None,
    kernel_input: Path | None = None,
) -> dict[str, Any]:
    smart_text = (
        smart_input.read_text(encoding="utf-8")
        if smart_input
        else _command("nvme", "smart-log", device)
    )
    kernel_text = (
        kernel_input.read_text(encoding="utf-8")
        if kernel_input
        else _command("dmesg", "--ctime")
    )
    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "device": device,
        "summary": summarize_storage_health(smart_text, kernel_text),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="/dev/nvme0")
    parser.add_argument("--smart-input", type=Path)
    parser.add_argument("--kernel-input", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/run/dimos/orin-nx-storage-health.json"),
    )
    args = parser.parse_args(argv)

    report = build_report(
        args.device,
        smart_input=args.smart_input,
        kernel_input=args.kernel_input,
    )
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["summary"]["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
