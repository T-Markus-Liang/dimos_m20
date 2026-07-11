"""Pure parsers for Linux process and cgroup memory evidence."""

from __future__ import annotations

import re
from typing import Any

_MAPPING_HEADER = re.compile(
    r"^[0-9a-f]+-[0-9a-f]+\s+\S+\s+\S+\s+\S+\s+\S+(?:\s+(.*))?$"
)


def parse_kb_fields(text: str) -> dict[str, int]:
    """Convert procfs `Key: N kB` fields to byte counts."""
    fields: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[0].endswith(":") and parts[2] == "kB":
            fields[parts[0][:-1]] = int(parts[1]) * 1024
    return fields


def parse_memory_stat(text: str) -> dict[str, int]:
    """Parse cgroup-v2 memory.stat key/value pairs."""
    fields: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2:
            fields[parts[0]] = int(parts[1])
    return fields


def parse_anonymous_mappings(text: str, minimum_bytes: int = 1024 * 1024) -> list[dict[str, Any]]:
    """Return resident anonymous mappings at or above the requested size."""
    mappings: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def finish() -> None:
        if current and current.get("anonymous_bytes", 0) >= minimum_bytes:
            mappings.append(current.copy())

    for line in text.splitlines():
        match = _MAPPING_HEADER.match(line)
        if match:
            finish()
            current = {
                "mapping": match.group(1) or "[anonymous]",
                "size_bytes": 0,
                "rss_bytes": 0,
                "anonymous_bytes": 0,
            }
            continue
        if current is None:
            continue
        parts = line.split()
        if len(parts) == 3 and parts[2] == "kB":
            key = parts[0][:-1]
            output_key = {
                "Size": "size_bytes",
                "Rss": "rss_bytes",
                "Anonymous": "anonymous_bytes",
            }.get(key)
            if output_key:
                current[output_key] = int(parts[1]) * 1024
    finish()
    return sorted(mappings, key=lambda item: item["anonymous_bytes"], reverse=True)
