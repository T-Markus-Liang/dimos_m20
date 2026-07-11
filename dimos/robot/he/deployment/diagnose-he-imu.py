#!/usr/bin/env python3
"""Capture bounded raw and filtered HE IMU streams and write JSON metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu

from dimos.robot.he.imu_data import summarize_imu_samples
from dimos.robot.he.visual_data import stamp_seconds


class ImuDiagnostic(Node):
    def __init__(self, topics: dict[str, str]) -> None:
        super().__init__("he_imu_diagnostic")
        self.samples: dict[str, dict[str, Any]] = {
            name: {
                "stamps": [],
                "quaternions": [],
                "gyroscopes": [],
                "accelerations": [],
                "orientation_covariances": [],
                "frame_ids": set(),
            }
            for name in topics
        }
        for name, topic in topics.items():
            self.create_subscription(
                Imu,
                topic,
                lambda message, stream=name: self._on_imu(stream, message),
                qos_profile_sensor_data,
            )

    def _on_imu(self, stream: str, message: Imu) -> None:
        sample = self.samples[stream]
        sample["stamps"].append(stamp_seconds(message))
        sample["quaternions"].append(
            [message.orientation.x, message.orientation.y, message.orientation.z, message.orientation.w]
        )
        sample["gyroscopes"].append(
            [message.angular_velocity.x, message.angular_velocity.y, message.angular_velocity.z]
        )
        sample["accelerations"].append(
            [message.linear_acceleration.x, message.linear_acceleration.y, message.linear_acceleration.z]
        )
        sample["orientation_covariances"].append(list(message.orientation_covariance))
        sample["frame_ids"].add(message.header.frame_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-topic", default="/ros_robot_controller/imu_raw")
    parser.add_argument("--filtered-topic")
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.duration <= 0.0:
        parser.error("--duration must be positive")

    topics = {"raw": args.raw_topic}
    if args.filtered_topic:
        topics["filtered"] = args.filtered_topic
    rclpy.init()
    node = ImuDiagnostic(topics)
    try:
        deadline = time.monotonic() + args.duration
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        missing = [
            name for name, sample in node.samples.items() if len(sample["stamps"]) < 2
        ]
        if missing:
            raise RuntimeError(f"insufficient IMU samples: {missing}")
        report = {
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "requested_duration_seconds": args.duration,
            "topics": topics,
            "streams": {
                name: summarize_imu_samples(**sample) for name, sample in node.samples.items()
            },
        }
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
