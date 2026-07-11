#!/usr/bin/env python3
"""Verify the live HE sensor feeds without enabling motion or raw point clouds."""

from __future__ import annotations

import argparse
import math
import statistics
import time
from typing import Any

import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Imu, LaserScan


def stamp_seconds(message: Any) -> float:
    return message.header.stamp.sec + message.header.stamp.nanosec / 1_000_000_000.0


def median_rate(messages: list[Any]) -> float:
    stamps = [stamp_seconds(message) for message in messages]
    intervals = [later - earlier for earlier, later in zip(stamps, stamps[1:])]
    positive = [interval for interval in intervals if interval > 0.0]
    if not positive:
        raise RuntimeError("message timestamps are not increasing")
    return 1.0 / statistics.median(positive)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(round((len(ordered) - 1) * fraction), len(ordered) - 1)]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-samples", type=int, default=30)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    require(args.scan_samples >= 3, "--scan-samples must be at least 3")

    rclpy.init()
    node = Node("he_sensor_quality_gate")
    scans: list[LaserScan] = []
    imus: list[Imu] = []
    odoms: list[Odometry] = []
    cameras: list[CameraInfo] = []
    subscriptions = [
        node.create_subscription(LaserScan, "/scan", scans.append, qos_profile_sensor_data),
        node.create_subscription(
            Imu, "/ros_robot_controller/imu_raw", imus.append, qos_profile_sensor_data
        ),
        node.create_subscription(Odometry, "/odom_raw", odoms.append, qos_profile_sensor_data),
        node.create_subscription(
            CameraInfo, "/aurora/rgb/camera_info", cameras.append, qos_profile_sensor_data
        ),
    ]

    try:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if len(scans) >= args.scan_samples and imus and odoms and cameras:
                break
        require(len(scans) >= args.scan_samples, f"received only {len(scans)} scan messages")
        require(imus, "received no IMU messages")
        require(odoms, "received no odometry messages")
        require(cameras, "received no RGB CameraInfo messages")

        scans = scans[: args.scan_samples]
        scan = scans[-1]
        now = time.time()
        require(scan.header.frame_id == "lidar_frame", f"unexpected scan frame: {scan.header.frame_id}")
        require(scan.angle_min <= 0.01, f"scan angle_min is not near zero: {scan.angle_min}")
        require(scan.angle_max - scan.angle_min >= 2.0 * math.pi - 0.05, "scan is not full 360 degrees")
        require(0.019 <= scan.range_min <= 0.021, f"unexpected range_min: {scan.range_min}")
        require(24.9 <= scan.range_max <= 25.1, f"unexpected range_max: {scan.range_max}")
        require(len(scan.ranges) >= 400, f"too few scan bins: {len(scan.ranges)}")
        require(abs(now - stamp_seconds(scan)) < 1.0, "scan timestamp is stale or clock is not synchronized")

        valid_ranges = [
            value
            for message in scans
            for value in message.ranges
            if math.isfinite(value) and message.range_min <= value <= message.range_max
        ]
        total_ranges = sum(len(message.ranges) for message in scans)
        valid_ratio = len(valid_ranges) / total_ranges
        require(valid_ratio >= 0.10, f"scan valid ratio is too low: {valid_ratio:.1%}")
        scan_hz = median_rate(scans)
        require(9.0 <= scan_hz <= 11.0, f"scan rate outside 9-11Hz: {scan_hz:.2f}Hz")

        imu = imus[-1]
        odom = odoms[-1]
        camera = cameras[-1]
        require(imu.header.frame_id == "imu_link", f"unexpected IMU frame: {imu.header.frame_id}")
        require(odom.header.frame_id == "odom", f"unexpected odom frame: {odom.header.frame_id}")
        require(
            odom.child_frame_id == "base_footprint",
            f"unexpected odom child frame: {odom.child_frame_id}",
        )
        require(
            camera.header.frame_id == "rgb_camera_link",
            f"unexpected RGB camera frame: {camera.header.frame_id}",
        )
        for name, message in (("IMU", imu), ("odom", odom), ("camera", camera)):
            require(
                abs(now - stamp_seconds(message)) < 1.0,
                f"{name} timestamp is stale or clock is not synchronized",
            )

        print("HE live sensor quality gate: PASS")
        print(
            f"LD19: frame=lidar_frame rate={scan_hz:.2f}Hz bins={len(scan.ranges)} "
            f"valid={valid_ratio:.1%} p05={percentile(valid_ranges, 0.05):.3f}m "
            f"median={statistics.median(valid_ranges):.3f}m "
            f"p95={percentile(valid_ranges, 0.95):.3f}m range=[{scan.range_min:.2f}, {scan.range_max:.1f}]m"
        )
        print(f"IMU: frame={imu.header.frame_id} observed={len(imus)}")
        print(
            f"odom_raw: frame={odom.header.frame_id}->{odom.child_frame_id} "
            f"observed={len(odoms)} status=UNTRUSTED(command-integrated)"
        )
        print(
            f"Aurora RGB CameraInfo: frame={camera.header.frame_id} "
            f"size={camera.width}x{camera.height} raw_pointcloud_subscription=NOT_REQUESTED"
        )
    finally:
        for subscription in subscriptions:
            node.destroy_subscription(subscription)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
