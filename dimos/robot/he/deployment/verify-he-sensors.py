#!/usr/bin/env python3
"""Verify every live Aurora feed plus HE IMU and open-loop odometry."""

from __future__ import annotations

import argparse
import statistics
import time
from typing import Any

import numpy as np
import rclpy
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image, Imu, PointCloud2


def stamp_seconds(message: Any) -> float:
    return message.header.stamp.sec + message.header.stamp.nanosec / 1_000_000_000.0


def median_rate(messages: list[Any]) -> float:
    stamps = [stamp_seconds(message) for message in messages]
    intervals = [later - earlier for earlier, later in zip(stamps, stamps[1:])]
    positive = [interval for interval in intervals if interval > 0.0]
    if not positive:
        raise RuntimeError("message timestamps are not increasing")
    return 1.0 / statistics.median(positive)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def require_image(message: Image, encoding: str, frame_id: str) -> None:
    require(message.encoding == encoding, f"unexpected {frame_id} encoding: {message.encoding}")
    require(message.width == 640 and message.height == 400, f"unexpected {frame_id} size")
    require(message.header.frame_id == frame_id, f"unexpected frame: {message.header.frame_id}")
    require(len(message.data) >= message.height * message.step, f"short {frame_id} payload")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-samples", type=int, default=5)
    parser.add_argument("--pointcloud-samples", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args()
    require(args.image_samples >= 3, "--image-samples must be at least 3")
    require(args.pointcloud_samples >= 1, "--pointcloud-samples must be positive")

    rclpy.init()
    node = Node("he_sensor_quality_gate")
    rgb: list[Image] = []
    depth: list[Image] = []
    ir: list[Image] = []
    points: list[PointCloud2] = []
    rgb_info: list[CameraInfo] = []
    depth_info: list[CameraInfo] = []
    imus: list[Imu] = []
    odoms: list[Odometry] = []
    subscriptions = [
        node.create_subscription(Image, "/aurora/rgb/image_raw", rgb.append, qos_profile_sensor_data),
        node.create_subscription(
            Image, "/aurora/depth/image_raw", depth.append, qos_profile_sensor_data
        ),
        node.create_subscription(Image, "/aurora/ir/image_raw", ir.append, qos_profile_sensor_data),
        node.create_subscription(PointCloud2, "/aurora/points2", points.append, qos_profile_sensor_data),
        node.create_subscription(
            CameraInfo, "/aurora/rgb/camera_info", rgb_info.append, qos_profile_sensor_data
        ),
        node.create_subscription(
            CameraInfo, "/aurora/ir/camera_info", depth_info.append, qos_profile_sensor_data
        ),
        node.create_subscription(
            Imu, "/ros_robot_controller/imu_raw", imus.append, qos_profile_sensor_data
        ),
        node.create_subscription(Odometry, "/odom_raw", odoms.append, qos_profile_sensor_data),
    ]

    try:
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if (
                len(rgb) >= args.image_samples
                and len(depth) >= args.image_samples
                and len(ir) >= args.image_samples
                and len(points) >= args.pointcloud_samples
                and rgb_info
                and depth_info
                and imus
                and odoms
            ):
                break

        for name, messages, count in (
            ("RGB", rgb, args.image_samples),
            ("depth", depth, args.image_samples),
            ("IR", ir, args.image_samples),
            ("point cloud", points, args.pointcloud_samples),
        ):
            require(len(messages) >= count, f"received only {len(messages)} {name} samples")
        require(rgb_info, "received no RGB CameraInfo")
        require(depth_info, "received no IR/depth CameraInfo")
        require(imus, "received no IMU messages")
        require(odoms, "received no odometry messages")

        rgb = rgb[: args.image_samples]
        depth = depth[: args.image_samples]
        ir = ir[: args.image_samples]
        points = points[: args.pointcloud_samples]
        require_image(rgb[-1], "bgr8", "rgb_camera_link")
        require_image(depth[-1], "mono16", "depth_camera_link")
        require_image(ir[-1], "mono8", "depth_camera_link")

        depth_rows = np.frombuffer(depth[-1].data, dtype=np.uint8).reshape(
            depth[-1].height, depth[-1].step
        )
        depth_values = np.frombuffer(
            np.ascontiguousarray(depth_rows[:, : depth[-1].width * 2]).tobytes(),
            dtype="<u2",
        )
        depth_valid_ratio = float(np.count_nonzero(depth_values)) / depth_values.size
        require(depth_valid_ratio >= 0.05, f"depth valid ratio is too low: {depth_valid_ratio:.1%}")

        cloud = points[-1]
        require(cloud.header.frame_id == "depth_camera_link", f"unexpected cloud frame: {cloud.header.frame_id}")
        require(cloud.width * cloud.height > 0, "Aurora point cloud is empty")
        fields = {field.name for field in cloud.fields}
        require({"x", "y", "z"}.issubset(fields), f"point cloud fields are incomplete: {fields}")

        color_calibration = rgb_info[-1]
        depth_calibration = depth_info[-1]
        require_image_info = (
            ("RGB", color_calibration, "rgb_camera_link"),
            ("IR/depth", depth_calibration, "depth_camera_link"),
        )
        for name, calibration, frame_id in require_image_info:
            require(calibration.width == 640 and calibration.height == 400, f"bad {name} calibration size")
            require(calibration.header.frame_id == frame_id, f"bad {name} calibration frame")
            require(calibration.distortion_model == "plumb_bob", f"bad {name} distortion model")
            require(calibration.k[0] > 0.0 and calibration.k[4] > 0.0, f"bad {name} intrinsics")

        imu = imus[-1]
        odom = odoms[-1]
        require(imu.header.frame_id == "imu_link", f"unexpected IMU frame: {imu.header.frame_id}")
        require(odom.header.frame_id == "odom", f"unexpected odom frame: {odom.header.frame_id}")
        require(odom.child_frame_id == "base_footprint", f"unexpected odom child: {odom.child_frame_id}")

        now = time.time()
        latest = (
            ("RGB", rgb[-1]),
            ("depth", depth[-1]),
            ("IR", ir[-1]),
            ("point cloud", cloud),
            ("RGB CameraInfo", color_calibration),
            ("depth CameraInfo", depth_calibration),
            ("IMU", imu),
            ("odom", odom),
        )
        for name, message in latest:
            require(abs(now - stamp_seconds(message)) < 2.0, f"{name} timestamp is stale")

        print("HE live sensor quality gate: PASS")
        print(
            f"Aurora RGB: bgr8 640x400 rate={median_rate(rgb):.2f}Hz; "
            f"depth: mono16 rate={median_rate(depth):.2f}Hz valid={depth_valid_ratio:.1%}; "
            f"IR: mono8 rate={median_rate(ir):.2f}Hz"
        )
        print(
            f"Aurora point cloud: frame={cloud.header.frame_id} "
            f"points={cloud.width * cloud.height}; calibrations=RGB+IR/depth"
        )
        print(f"IMU: frame={imu.header.frame_id} observed={len(imus)}")
        print(
            f"odom_raw: frame={odom.header.frame_id}->{odom.child_frame_id} "
            f"observed={len(odoms)} status=UNTRUSTED(command-integrated)"
        )
    finally:
        for subscription in subscriptions:
            node.destroy_subscription(subscription)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
