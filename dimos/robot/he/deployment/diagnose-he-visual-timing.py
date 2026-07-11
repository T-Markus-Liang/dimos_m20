#!/usr/bin/env python3
"""Measure long-running Aurora/IMU timing without retaining sensor payloads."""

from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import resource
import time
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, Imu, PointCloud2

from dimos.robot.he.visual_data import (
    stamp_seconds,
    timestamp_alignment,
    timing_series_quality,
)

TOPICS = {
    "rgb": (Image, "/aurora/rgb/image_raw"),
    "depth": (Image, "/aurora/depth/image_raw"),
    "ir": (Image, "/aurora/ir/image_raw"),
    "pointcloud": (PointCloud2, "/aurora/points2"),
    "imu": (Imu, "/ros_robot_controller/imu_raw"),
}


class VisualTimingDiagnostic(Node):
    def __init__(self, max_samples: int) -> None:
        super().__init__("he_visual_timing_diagnostic")
        self.collecting = False
        self.stamps = {name: deque(maxlen=max_samples) for name in TOPICS}
        self.receipts = {name: deque(maxlen=max_samples) for name in TOPICS}
        self.total_samples = {name: 0 for name in TOPICS}
        self.frames: dict[str, str] = {}
        for name, (message_type, topic) in TOPICS.items():
            self.create_subscription(
                message_type,
                topic,
                lambda message, stream=name: self._on_message(stream, message),
                qos_profile_sensor_data,
            )

    def _on_message(self, stream: str, message: Any) -> None:
        if not self.collecting:
            return
        self.stamps[stream].append(stamp_seconds(message))
        self.receipts[stream].append(self.get_clock().now().nanoseconds / 1_000_000_000.0)
        self.total_samples[stream] += 1
        self.frames[stream] = message.header.frame_id

    def navigation_publishers(self) -> int:
        return len(self.get_publishers_info_by_topic("/he/nav_cmd_vel"))


def process_rss_mib() -> dict[str, float]:
    current_kib = 0
    with Path("/proc/self/status").open(encoding="utf-8") as stream:
        for line in stream:
            if line.startswith("VmRSS:"):
                current_kib = int(line.split()[1])
                break
    return {
        "current": current_kib / 1024.0,
        "peak": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
    }


def summarize(node: VisualTimingDiagnostic, duration: float) -> dict[str, Any]:
    streams = {}
    for name in TOPICS:
        stamps = list(node.stamps[name])
        receipts = list(node.receipts[name])
        if len(stamps) < 2:
            raise RuntimeError(f"insufficient {name} timing samples: {len(stamps)}")
        streams[name] = {
            **timing_series_quality(stamps, receipts),
            "total_samples": node.total_samples[name],
            "retained_samples": len(stamps),
            "truncated": node.total_samples[name] > len(stamps),
        }
    rgb_stamps = list(node.stamps["rgb"])
    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "duration_seconds": duration,
        "frames": node.frames,
        "streams": streams,
        "rgb_nearest_timestamp_alignment": {
            name: timestamp_alignment(rgb_stamps, list(node.stamps[name]))
            for name in ("depth", "ir", "pointcloud", "imu")
        },
        "process_rss_mib": process_rss_mib(),
        "navigation_publishers": node.navigation_publishers(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=120.0)
    parser.add_argument("--warmup", type=float, default=3.0)
    parser.add_argument("--max-samples-per-stream", type=int, default=200_000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 10.0 <= args.duration <= 3600.0:
        parser.error("--duration must be between 10 and 3600 seconds")
    if not 0.0 <= args.warmup <= 30.0:
        parser.error("--warmup must be between 0 and 30 seconds")
    if not 100 <= args.max_samples_per_stream <= 200_000:
        parser.error("--max-samples-per-stream must be between 100 and 200000")

    rclpy.init()
    node = VisualTimingDiagnostic(args.max_samples_per_stream)
    try:
        warmup_deadline = time.monotonic() + args.warmup
        while time.monotonic() < warmup_deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        if node.navigation_publishers():
            raise RuntimeError("refusing timing capture while /he/nav_cmd_vel has publishers")

        node.collecting = True
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        node.collecting = False
        report = summarize(node, args.duration)
        if report["navigation_publishers"]:
            raise RuntimeError("/he/nav_cmd_vel gained a publisher during timing capture")
    finally:
        node.destroy_node()
        rclpy.shutdown()

    rendered = json.dumps(report, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
