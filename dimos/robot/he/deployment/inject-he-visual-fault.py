#!/usr/bin/env python3
"""Publish bounded fresh visual faults on isolated HE ROS topics."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import time
from typing import Any

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import CameraInfo, Image

from dimos.robot.he.visual_data import VISUAL_FAULT_MODES, visual_fault_payload


class HEVisualFaultProxy(Node):
    def __init__(self, mode: str, baseline_s: float, fault_s: float, recovery_s: float) -> None:
        super().__init__("he_visual_fault_proxy")
        self.mode = mode
        self.baseline_s = baseline_s
        self.fault_s = fault_s
        self.recovery_s = recovery_s
        self.started_monotonic: float | None = None
        self.started_epoch: float | None = None
        self.events: list[dict[str, Any]] = []
        self.counts: Counter[tuple[str, str]] = Counter()
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.image_publishers = {
            "rgb": self.create_publisher(Image, "/he/fault/rgb/image_raw", qos),
            "depth": self.create_publisher(Image, "/he/fault/depth/image_raw", qos),
        }
        self.info_publishers = {
            "rgb": self.create_publisher(CameraInfo, "/he/fault/rgb/camera_info", qos),
            "depth": self.create_publisher(CameraInfo, "/he/fault/depth/camera_info", qos),
        }
        self.create_subscription(
            Image,
            "/aurora/rgb/image_raw",
            lambda message: self._image("rgb", message),
            qos,
        )
        self.create_subscription(
            Image,
            "/aurora/depth/image_raw",
            lambda message: self._image("depth", message),
            qos,
        )
        self.create_subscription(
            CameraInfo,
            "/aurora/rgb/camera_info",
            lambda message: self._camera_info("rgb", message),
            qos,
        )
        self.create_subscription(
            CameraInfo,
            "/aurora/ir/camera_info",
            lambda message: self._camera_info("depth", message),
            qos,
        )
        self.create_timer(0.1, self._start_when_subscribed)

    @property
    def total_duration_s(self) -> float:
        return self.baseline_s + self.fault_s + self.recovery_s

    def _start_when_subscribed(self) -> None:
        if self.started_monotonic is not None:
            return
        if all(publisher.get_subscription_count() > 0 for publisher in self.image_publishers.values()):
            self.started_monotonic = time.monotonic()
            self.started_epoch = time.time()
            self.events.append({"phase": "baseline", "at": self.started_epoch})

    def phase(self) -> str:
        if self.started_monotonic is None:
            return "waiting"
        elapsed = time.monotonic() - self.started_monotonic
        if elapsed < self.baseline_s:
            return "baseline"
        if elapsed < self.baseline_s + self.fault_s:
            return "fault"
        if elapsed < self.total_duration_s:
            return "recovery"
        return "complete"

    def record_phase_transition(self, previous: str) -> str:
        current = self.phase()
        if current != previous:
            self.events.append({"phase": current, "at": time.time()})
        return current

    def _image(self, stream: str, message: Image) -> None:
        phase = self.phase()
        if phase == "fault":
            message.data = visual_fault_payload(message.data, stream, self.mode)
        self.image_publishers[stream].publish(message)
        self.counts[(phase, stream)] += 1

    def _camera_info(self, stream: str, message: CameraInfo) -> None:
        self.info_publishers[stream].publish(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(VISUAL_FAULT_MODES), required=True)
    parser.add_argument("--baseline", type=float, default=10.0)
    parser.add_argument("--fault-duration", type=float, default=8.0)
    parser.add_argument("--recovery", type=float, default=10.0)
    parser.add_argument("--subscriber-timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.baseline, args.fault_duration, args.recovery, args.subscriber_timeout) <= 0.0:
        parser.error("all durations must be positive")

    rclpy.init()
    node = HEVisualFaultProxy(args.mode, args.baseline, args.fault_duration, args.recovery)
    wait_deadline = time.monotonic() + args.subscriber_timeout
    try:
        while node.started_monotonic is None and time.monotonic() < wait_deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
        if node.started_monotonic is None:
            raise RuntimeError("fault proxy timed out waiting for RGB and depth subscribers")
        previous_phase = "baseline"
        while node.phase() != "complete":
            rclpy.spin_once(node, timeout_sec=0.05)
            previous_phase = node.record_phase_transition(previous_phase)
        node.record_phase_transition(previous_phase)
        report = {
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "mode": args.mode,
            "durations_seconds": {
                "baseline": args.baseline,
                "fault": args.fault_duration,
                "recovery": args.recovery,
            },
            "events": node.events,
            "image_counts": {
                f"{phase}.{stream}": count
                for (phase, stream), count in sorted(node.counts.items())
            },
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
