#!/usr/bin/env python3
"""Exercise HEConnection over ROS without touching the real chassis topic."""

import asyncio
from collections.abc import Callable
import math
import time

import rclpy
from geometry_msgs.msg import Twist as RosTwist
from rclpy.node import Node

from dimos.msgs.geometry_msgs.Twist import Twist
from dimos.robot.he.connection import HEConnection


TEST_TOPIC = "/he_safety_test/cmd_vel"
REAL_TOPIC = "/cmd_vel"


def spin_until(node: Node, condition: Callable[[], bool], timeout_s: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_s
    while not condition() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.05)
    if not condition():
        raise RuntimeError("timed out waiting for ROS dry-run message")


def main() -> None:
    if TEST_TOPIC == REAL_TOPIC or not TEST_TOPIC.startswith("/he_safety_test/"):
        raise RuntimeError("dry-run topic guard failed")

    connection = HEConnection(
        enabled=True,
        ros_cmd_vel_topic=TEST_TOPIC,
        max_linear_mps=0.10,
        max_angular_radps=0.30,
        cmd_timeout_s=0.20,
    )
    connection._start_ros_publisher()
    probe = Node("he_safety_test_probe")
    received: list[RosTwist] = []
    subscription = probe.create_subscription(RosTwist, TEST_TOPIC, received.append, 10)

    try:
        if probe.count_publishers(REAL_TOPIC) != 0:
            raise RuntimeError("real /cmd_vel already has a publisher; refusing dry run")

        spin_until(probe, lambda: probe.count_publishers(TEST_TOPIC) == 1)

        asyncio.run(
            connection.handle_cmd_vel(
                Twist(linear=[0.50, 0.20, 0.0], angular=[0.0, 0.0, -1.0])
            )
        )
        connection._publish(connection._fresh_command())
        spin_until(probe, lambda: len(received) >= 1)

        first = received[0]
        assert math.isclose(first.linear.x, 0.10, abs_tol=1e-6)
        assert math.isclose(first.linear.y, 0.0, abs_tol=1e-6)
        assert math.isclose(first.angular.z, -0.30, abs_tol=1e-6)

        time.sleep(0.25)
        connection._publish(connection._fresh_command())
        spin_until(probe, lambda: len(received) >= 2)
        assert received[1].linear.x == 0.0
        assert received[1].angular.z == 0.0

        connection._publish_stop()
        spin_until(probe, lambda: len(received) >= 3)
        assert received[-1].linear.x == 0.0
        assert received[-1].angular.z == 0.0

        if probe.count_publishers(REAL_TOPIC) != 0:
            raise RuntimeError("real /cmd_vel publisher appeared during dry run")

        print("HE isolated ROS control dry run: PASS")
        print("fresh command: linear.x=0.10 angular.z=-0.30")
        print("watchdog and shutdown command: zero")
        print("real /cmd_vel publishers: 0")
    finally:
        probe.destroy_subscription(subscription)
        probe.destroy_node()
        connection._destroy_ros_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
