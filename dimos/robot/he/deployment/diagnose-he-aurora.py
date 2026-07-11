#!/usr/bin/env python3
"""Capture bounded Aurora samples and report SLAM-relevant timing/depth quality."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, Imu, PointCloud2

from dimos.robot.he.visual_data import (
    depth_array,
    depth_ir_quality,
    depth_quality,
    depth_temporal_quality,
    mono8_array,
    pointcloud_xyz_quality,
    stamp_seconds,
    timestamp_alignment,
    topic_rate,
)

TOPICS = {
    "rgb": (Image, "/aurora/rgb/image_raw"),
    "depth": (Image, "/aurora/depth/image_raw"),
    "ir": (Image, "/aurora/ir/image_raw"),
    "pointcloud": (PointCloud2, "/aurora/points2"),
    "imu": (Imu, "/ros_robot_controller/imu_raw"),
}


class AuroraDiagnostic(Node):
    def __init__(self, samples: int) -> None:
        super().__init__("he_aurora_diagnostic")
        self.samples = samples
        self.stamps: dict[str, list[float]] = {name: [] for name in TOPICS}
        self.depth_frames: list[np.ndarray] = []
        self.ir_frames: list[tuple[float, np.ndarray]] = []
        self.pointcloud_frames: list[PointCloud2] = []
        self.frames: dict[str, str] = {}
        for name, (message_type, topic) in TOPICS.items():
            self.create_subscription(
                message_type,
                topic,
                lambda message, stream=name: self._on_message(stream, message),
                qos_profile_sensor_data,
            )

    def _on_message(self, stream: str, message: Any) -> None:
        self.stamps[stream].append(stamp_seconds(message))
        self.frames[stream] = message.header.frame_id
        if stream == "depth":
            self.depth_frames.append(depth_array(message))
        elif stream == "ir":
            self.ir_frames.append((stamp_seconds(message), mono8_array(message)))
        elif stream == "pointcloud":
            self.pointcloud_frames.append(message)

    def complete(self) -> bool:
        return all(len(stamps) >= self.samples for stamps in self.stamps.values())


def summarize(node: AuroraDiagnostic) -> dict[str, Any]:
    rates = {name: topic_rate(stamps) for name, stamps in node.stamps.items()}
    alignments = {
        name: timestamp_alignment(node.stamps["rgb"], node.stamps[name])
        for name in ("depth", "ir", "pointcloud", "imu")
    }
    depth_reports = [depth_quality(frame) for frame in node.depth_frames]
    latest_depth_stamp = node.stamps["depth"][-1]
    nearest_ir_stamp, nearest_ir = min(
        node.ir_frames, key=lambda item: abs(item[0] - latest_depth_stamp)
    )
    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "samples": {name: len(stamps) for name, stamps in node.stamps.items()},
        "frames": node.frames,
        "rates_hz": rates,
        "rgb_nearest_timestamp_alignment": alignments,
        "depth": {
            "valid_ratio_median": float(np.median([item["valid_ratio"] for item in depth_reports])),
            "center_40_percent_valid_ratio_median": float(
                np.median([item["center_40_percent_valid_ratio"] for item in depth_reports])
            ),
            "latest": depth_reports[-1],
            "temporal": depth_temporal_quality(node.depth_frames),
            "nearest_ir": {
                "absolute_timestamp_offset_ms": abs(nearest_ir_stamp - latest_depth_stamp) * 1000.0,
                **depth_ir_quality(node.depth_frames[-1], nearest_ir),
            },
        },
        "pointcloud_latest": pointcloud_xyz_quality(node.pointcloud_frames[-1]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.samples < 2:
        parser.error("--samples must be at least 2")

    rclpy.init()
    node = AuroraDiagnostic(args.samples)
    deadline = time.monotonic() + args.timeout
    try:
        while not node.complete() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        missing = {name: len(stamps) for name, stamps in node.stamps.items() if len(stamps) < 2}
        if missing:
            raise RuntimeError(f"insufficient sensor samples: {missing}")
        report = summarize(node)
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
