#!/usr/bin/env python3
"""Run the first real HEConnection pulse with the vehicle lifted."""

import argparse
import asyncio
import threading
import time

from geometry_msgs.msg import Twist as RosTwist
import rclpy
from rclpy.node import Node
from ros_robot_controller_msgs.msg import MotorsState, SetPWMServoState

from dimos.msgs.geometry_msgs.Twist import Twist
from dimos.robot.he.connection import HEConnection


def motor_values(message: MotorsState) -> list[tuple[int, float]]:
    return [(state.id, state.rps) for state in message.data]


def servo_values(message: SetPWMServoState) -> list[tuple[list[int], list[int]]]:
    return [(list(state.id), list(state.position)) for state in message.state]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-lifted", action="store_true")
    parser.add_argument(
        "--case",
        choices=("forward", "reverse", "left", "right"),
        default="forward",
    )
    args = parser.parse_args()
    if not args.confirm_lifted:
        raise RuntimeError("refusing real motion without --confirm-lifted")

    rclpy.init()
    probe = Node("he_lifted_control_gate_probe")
    cmd_samples: list[tuple[float, RosTwist]] = []
    motor_samples: list[tuple[float, MotorsState]] = []
    servo_samples: list[tuple[float, SetPWMServoState]] = []
    cmd_sub = probe.create_subscription(
        RosTwist,
        "/he/final_cmd_vel",
        lambda message: cmd_samples.append((time.monotonic(), message)),
        50,
    )
    motor_sub = probe.create_subscription(
        MotorsState,
        "/ros_robot_controller/set_motor",
        lambda message: motor_samples.append((time.monotonic(), message)),
        50,
    )
    servo_sub = probe.create_subscription(
        SetPWMServoState,
        "/ros_robot_controller/pwm_servo/set_state",
        lambda message: servo_samples.append((time.monotonic(), message)),
        50,
    )
    stop_spin = threading.Event()
    spin_thread = threading.Thread(
        target=lambda: _spin(probe, stop_spin),
        daemon=True,
    )
    spin_thread.start()

    connection = HEConnection(
        enabled=True,
        ros_cmd_vel_topic="/he/nav_cmd_vel",
        max_linear_mps=0.03,
        max_angular_radps=0.10,
        cmd_rate_hz=20.0,
        cmd_timeout_s=0.20,
    )

    try:
        time.sleep(0.5)
        if probe.count_publishers("/he/nav_cmd_vel") != 0:
            raise RuntimeError("/he/nav_cmd_vel already has a publisher")
        if probe.count_publishers("/controller/cmd_vel") != 0:
            raise RuntimeError("joystick command publisher is still active")

        connection._start_ros_publisher()
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if (
                probe.count_publishers("/he/nav_cmd_vel") == 1
                and probe.count_publishers("/ros_robot_controller/set_motor") >= 1
                and probe.count_publishers("/ros_robot_controller/pwm_servo/set_state") == 1
            ):
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("ROS endpoint discovery failed")
        time.sleep(0.5)

        for _ in range(10):
            connection._publish(Twist.zero())
            time.sleep(0.05)

        command_by_case = {
            "forward": (0.03, 0.0),
            "reverse": (-0.03, 0.0),
            "left": (0.03, 0.10),
            "right": (0.03, -0.10),
        }
        linear_x, angular_z = command_by_case[args.case]
        command_time = time.monotonic()
        asyncio.run(
            connection.handle_cmd_vel(
                Twist(linear=[linear_x, 0.0, 0.0], angular=[0.0, 0.0, angular_z])
            )
        )
        for _ in range(16):
            connection._publish(connection._fresh_command())
            time.sleep(0.05)

        connection._publish_stop()
        time.sleep(0.5)

        nonzero_cmd = [
            (stamp, message.linear.x)
            for stamp, message in cmd_samples
            if stamp >= command_time and abs(message.linear.x) > 1e-6
        ]
        nonzero_motor = [
            (stamp, motor_values(message))
            for stamp, message in motor_samples
            if stamp >= command_time
            and any(abs(rps) > 1e-6 for _, rps in motor_values(message))
        ]
        tail_motor = [motor_values(message) for _, message in motor_samples[-5:]]
        noncenter_servo = [
            (stamp, servo_values(message))
            for stamp, message in servo_samples
            if stamp >= command_time
            and any(position != [1500] for _, position in servo_values(message))
        ]
        tail_servo = [servo_values(message) for _, message in servo_samples[-3:]]

        if not nonzero_cmd:
            raise RuntimeError("no nonzero /he/final_cmd_vel sample observed")
        if not nonzero_motor:
            raise RuntimeError("no nonzero downstream motor command observed")
        if len(tail_motor) < 5:
            raise RuntimeError("fewer than five final motor samples observed")
        if any(abs(rps) > 1e-6 for sample in tail_motor for _, rps in sample):
            raise RuntimeError(f"motor output did not settle to zero: {tail_motor}")
        if args.case in ("left", "right") and not noncenter_servo:
            raise RuntimeError("no steering command observed")
        if len(tail_servo) < 3:
            raise RuntimeError("fewer than three final steering samples observed")
        if any(position != [1500] for sample in tail_servo for _, position in sample):
            raise RuntimeError(f"steering did not return to center: {tail_servo}")

        last_nonzero_time = nonzero_motor[-1][0]
        zero_after = [
            stamp
            for stamp, message in motor_samples
            if stamp > last_nonzero_time
            and all(abs(rps) <= 1e-6 for _, rps in motor_values(message))
        ]
        if not zero_after:
            raise RuntimeError("no downstream zero observed after motion")

        print(f"HE lifted {args.case} pulse: PASS")
        print("first_nonzero_motor", nonzero_motor[0][1])
        if noncenter_servo:
            print("first_noncenter_servo", noncenter_servo[0][1])
        print("downstream_zero_delay_s", round(zero_after[0] - command_time, 3))
        print("tail_motor", tail_motor)
        print("tail_servo", tail_servo)
    finally:
        connection._publish_stop()
        connection._destroy_ros_node()
        stop_spin.set()
        spin_thread.join(timeout=1.0)
        probe.destroy_subscription(cmd_sub)
        probe.destroy_subscription(motor_sub)
        probe.destroy_subscription(servo_sub)
        probe.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


def _spin(node: Node, stop: threading.Event) -> None:
    while not stop.is_set():
        rclpy.spin_once(node, timeout_sec=0.05)


if __name__ == "__main__":
    main()
