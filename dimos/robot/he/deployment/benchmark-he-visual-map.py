#!/usr/bin/env python3
"""Measure bounded HE occupancy output and its isolated dynamic TF chain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import rclpy
from nav_msgs.msg import OccupancyGrid
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from tf2_ros import Buffer, TransformException, TransformListener

from dimos.robot.he.visual_data import (
    occupancy_grid_metrics,
    stamp_seconds,
    stationary_trajectory_metrics,
    topic_rate,
)


class VisualMapBenchmark(Node):
    def __init__(self, map_topic: str, map_frame: str, base_frame: str) -> None:
        super().__init__("he_visual_map_benchmark")
        map_qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.maps: list[OccupancyGrid] = []
        self.tf_stamps: list[float] = []
        self.tf_positions: list[list[float]] = []
        self.tf_orientations: list[list[float]] = []
        self.tf_latencies: list[float] = []
        self.tf_lookup_failures = 0
        self.map_frame = map_frame
        self.base_frame = base_frame
        self.create_subscription(OccupancyGrid, map_topic, self.maps.append, map_qos)
        self.tf_buffer = Buffer(cache_time=Duration(seconds=10.0))
        self.tf_listener = TransformListener(self.tf_buffer, self)

    def sample_tf(self) -> None:
        try:
            transform = self.tf_buffer.lookup_transform(self.map_frame, self.base_frame, Time())
        except TransformException:
            self.tf_lookup_failures += 1
            return
        stamp = stamp_seconds(transform)
        if self.tf_stamps and stamp == self.tf_stamps[-1]:
            return
        value = transform.transform
        self.tf_stamps.append(stamp)
        self.tf_positions.append([value.translation.x, value.translation.y, value.translation.z])
        self.tf_orientations.append(
            [value.rotation.x, value.rotation.y, value.rotation.z, value.rotation.w]
        )
        now = self.get_clock().now().nanoseconds / 1e9
        self.tf_latencies.append(max(0.0, now - stamp))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map-topic", default="/he/visual_occupancy")
    parser.add_argument("--map-frame", default="he_map")
    parser.add_argument("--base-frame", default="base_link")
    parser.add_argument("--duration", type=float, default=15.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.duration <= 0.0:
        parser.error("--duration must be positive")

    rclpy.init()
    node = VisualMapBenchmark(args.map_topic, args.map_frame, args.base_frame)
    deadline = time.monotonic() + args.duration
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            node.sample_tf()
        if not node.maps:
            raise RuntimeError("no occupancy maps received")
        latest = node.maps[-1]
        report = {
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "requested_duration_seconds": args.duration,
            "maps_received": len(node.maps),
            "map_frame": latest.header.frame_id,
            "map": occupancy_grid_metrics(
                list(latest.data), latest.info.width, latest.info.height, latest.info.resolution
            ),
            "tf_lookup_failures": node.tf_lookup_failures,
            "tf_chain": stationary_trajectory_metrics(
                node.tf_stamps,
                node.tf_positions,
                node.tf_orientations,
                node.tf_latencies,
            ),
        }
        map_stamps = [stamp_seconds(message) for message in node.maps]
        if len(map_stamps) > 1:
            report["map_update_rate_hz"] = topic_rate(map_stamps)
    finally:
        node.destroy_node()
        rclpy.shutdown()

    rendered = json.dumps(report, indent=2, sort_keys=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
