#!/usr/bin/env python3
"""Measure a bounded visual-odometry shadow run without publishing commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import time
from typing import Any

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rtabmap_msgs.msg import OdomInfo

from dimos.robot.he.visual_data import stamp_seconds, stationary_trajectory_metrics


class VisualOdomBenchmark(Node):
    def __init__(self, odom_topic: str, info_topic: str) -> None:
        super().__init__("he_visual_odom_benchmark")
        self.stamps: list[float] = []
        self.positions: list[list[float]] = []
        self.orientations: list[list[float]] = []
        self.latencies: list[float] = []
        self.frame_ids: set[tuple[str, str]] = set()
        self.info: list[dict[str, Any]] = []
        self.create_subscription(Odometry, odom_topic, self._on_odom, qos_profile_sensor_data)
        self.create_subscription(OdomInfo, info_topic, self._on_info, qos_profile_sensor_data)

    def _on_odom(self, message: Odometry) -> None:
        stamp = stamp_seconds(message)
        pose = message.pose.pose
        self.stamps.append(stamp)
        self.positions.append([pose.position.x, pose.position.y, pose.position.z])
        self.orientations.append(
            [pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w]
        )
        self.latencies.append(max(0.0, self.get_clock().now().nanoseconds / 1e9 - stamp))
        self.frame_ids.add((message.header.frame_id, message.child_frame_id))

    def _on_info(self, message: OdomInfo) -> None:
        self.info.append(
            {
                "lost": bool(message.lost),
                "inliers": int(message.inliers),
                "matches": int(message.matches),
                "features": int(message.features),
                "time_estimation_seconds": float(message.time_estimation),
                "memory_usage_mb": int(message.memory_usage),
            }
        )


def info_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {"samples": 0}
    return {
        "samples": len(samples),
        "lost_count": sum(item["lost"] for item in samples),
        "inliers_median": statistics.median(item["inliers"] for item in samples),
        "inliers_min": min(item["inliers"] for item in samples),
        "features_median": statistics.median(item["features"] for item in samples),
        "time_estimation_median_ms": statistics.median(
            item["time_estimation_seconds"] for item in samples
        )
        * 1000.0,
        "time_estimation_p95_ms": sorted(
            item["time_estimation_seconds"] for item in samples
        )[int((len(samples) - 1) * 0.95)]
        * 1000.0,
        "reported_memory_max_mb": max(item["memory_usage_mb"] for item in samples),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--odom-topic", default="/he/visual_odom")
    parser.add_argument("--info-topic", default="/he/visual_odom_info")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration <= 0.0:
        parser.error("--duration must be positive")

    rclpy.init()
    node = VisualOdomBenchmark(args.odom_topic, args.info_topic)
    deadline = time.monotonic() + args.duration
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        metrics = stationary_trajectory_metrics(
            node.stamps, node.positions, node.orientations, node.latencies
        )
        report = {
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "requested_duration_seconds": args.duration,
            "frame_ids": sorted(node.frame_ids),
            "trajectory": metrics,
            "odometry_info": info_summary(node.info),
        }
    finally:
        node.destroy_node()
        rclpy.shutdown()

    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
