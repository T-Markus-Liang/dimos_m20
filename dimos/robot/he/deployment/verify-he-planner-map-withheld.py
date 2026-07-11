#!/usr/bin/env python3
"""Verify that unhealthy HE localization withholds planner-facing maps."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

from dimos.core.transport import LCMTransport, pLCMTransport
from dimos.msgs.nav_msgs.OccupancyGrid import OccupancyGrid
from dimos.robot.he.visual_slam import (
    LocalizationHealth,
    summarize_planner_map_withholding,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 5.0 <= args.duration <= 120.0:
        parser.error("--duration must be between 5 and 120 seconds")

    visual_map_receipts: list[float] = []
    global_costmap_receipts: list[float] = []
    health_samples: list[dict[str, Any]] = []
    visual_map = LCMTransport("/visual_map", OccupancyGrid)
    global_costmap = LCMTransport("/global_costmap", OccupancyGrid)
    health: pLCMTransport[LocalizationHealth] = pLCMTransport("/localization_health")

    unsubscribe = (
        visual_map.subscribe(lambda _: visual_map_receipts.append(time.time())),
        global_costmap.subscribe(lambda _: global_costmap_receipts.append(time.time())),
        health.subscribe(
            lambda message: health_samples.append(
                {
                    "received_at": time.time(),
                    "healthy": message.healthy,
                    "reasons": message.reasons,
                }
            )
        ),
    )
    started = time.monotonic()
    try:
        deadline = started + args.duration
        while time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        for stop in unsubscribe:
            stop()
        visual_map.stop()
        global_costmap.stop()
        health.stop()

    report = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_seconds": time.monotonic() - started,
        "summary": summarize_planner_map_withholding(
            visual_map_receipts, global_costmap_receipts, health_samples
        ),
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()

