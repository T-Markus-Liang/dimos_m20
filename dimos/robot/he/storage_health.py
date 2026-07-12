"""Fail-closed parsing for HE NVMe and kernel storage evidence."""

from __future__ import annotations

import re
from typing import Any

_KERNEL_FAILURE = re.compile(
    r"critical medium error|EXT4-fs error|I/O error.*nvme|blk_update_request.*error",
    re.IGNORECASE,
)


def _integer(value: str) -> int:
    cleaned = value.strip().rstrip("%").replace(",", "")
    return int(cleaned, 0)


def parse_nvme_smart(text: str) -> dict[str, int]:
    """Extract the SMART fields used by the HE storage admission gate."""
    values: dict[str, int] = {}
    wanted = {
        "critical_warning",
        "available_spare",
        "available_spare_threshold",
        "media_errors",
        "unsafe_shutdowns",
    }
    for line in text.splitlines():
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        name = name.strip()
        if name in wanted:
            values[name] = _integer(value.split()[0])
    missing = sorted(wanted - values.keys())
    if missing:
        raise ValueError(f"missing NVMe SMART fields: {', '.join(missing)}")
    return values


def summarize_storage_health(smart_text: str, kernel_text: str) -> dict[str, Any]:
    """Return explicit reasons that forbid HE runtime startup."""
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
