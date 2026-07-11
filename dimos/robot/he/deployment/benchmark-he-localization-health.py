#!/usr/bin/env python3
"""Record bounded DimOS localization-health state without publishing messages."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time
from typing import Any

from dimos.core.transport import pLCMTransport
from dimos.robot.he.visual_slam import LocalizationHealth, summarize_localization_health


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="/localization_health")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration <= 0.0:
        parser.error("--duration must be positive")

    samples: list[dict[str, Any]] = []
    transport: pLCMTransport[LocalizationHealth] = pLCMTransport(args.topic)

    def capture(message: LocalizationHealth) -> None:
        samples.append({"received_at": time.time(), **asdict(message)})

    unsubscribe = transport.subscribe(capture)
    started_at = time.time()
    try:
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            time.sleep(0.05)
    finally:
        unsubscribe()
        transport.stop()

    if not samples:
        raise RuntimeError("no localization health samples received")

    report = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "requested_duration_seconds": args.duration,
        "actual_duration_seconds": time.time() - started_at,
        "topic": args.topic,
        "summary": summarize_localization_health(samples),
        "samples": samples,
    }
    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
