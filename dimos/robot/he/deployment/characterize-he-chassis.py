#!/usr/bin/env python3
"""Characterize the lifted HE command chain without claiming physical feedback."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import statistics
import threading
import time
from typing import Any

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.node import Node
from ros_robot_controller_msgs.msg import MotorsState, SetPWMServoState


WHEELBASE_M = 0.17706
TRACK_WIDTH_M = 0.17165
WHEEL_DIAMETER_M = 0.085
MAX_LINEAR_MPS = 0.10
MAX_ANGULAR_RADPS = 0.30
PUBLISH_HZ = 20.0


def clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def expected_output(linear_x: float, angular_z: float) -> dict[str, Any]:
    linear_x = clamp(linear_x, MAX_LINEAR_MPS)
    angular_z = clamp(angular_z, MAX_ANGULAR_RADPS)
    if abs(linear_x) < 1e-8:
        angular_z = 0.0
        steering_deg = 0.0
        pwm = 1500
        motor = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0}
    else:
        steering_rad = (
            math.atan(WHEELBASE_M * angular_z / linear_x)
            if abs(angular_z) >= 1e-8
            else 0.0
        )
        steering_rad = clamp(steering_rad, math.radians(34.0))
        steering_deg = math.degrees(steering_rad)
        pwm = int(1500 + 2000 * math.degrees(-steering_rad) / 180)
        left_mps = linear_x - angular_z * TRACK_WIDTH_M / 2
        right_mps = linear_x + angular_z * TRACK_WIDTH_M / 2
        motor = {
            1: 0.0,
            2: left_mps / (math.pi * WHEEL_DIAMETER_M),
            3: 0.0,
            4: -right_mps / (math.pi * WHEEL_DIAMETER_M),
        }
    return {
        "linear_x": linear_x,
        "angular_z": angular_z,
        "steering_deg": steering_deg,
        "pwm": pwm,
        "motor_rps": motor,
    }


def first_after(samples: list[tuple[Any, ...]], stamp: float, predicate: Any) -> tuple[Any, ...]:
    for sample in samples:
        if sample[0] >= stamp and predicate(sample):
            return sample
    raise RuntimeError("expected downstream sample was not observed")


def optional_first_after(
    samples: list[tuple[Any, ...]], stamp: float, predicate: Any
) -> tuple[Any, ...] | None:
    for sample in samples:
        if sample[0] >= stamp and predicate(sample):
            return sample
    return None


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(round((len(ordered) - 1) * fraction), len(ordered) - 1)]


def stats_ms(values: list[float]) -> dict[str, float]:
    return {
        "count": len(values),
        "median_ms": round(statistics.median(values) * 1000, 3),
        "p95_ms": round(percentile(values, 0.95) * 1000, 3),
        "max_ms": round(max(values) * 1000, 3),
    }


class Probe:
    def __init__(self) -> None:
        self.node = Node("he_chassis_characterization_probe")
        self.final_cmd: list[tuple[float, float, float]] = []
        self.motor: list[tuple[float, dict[int, float]]] = []
        self.servo: list[tuple[float, int]] = []
        self.odom: list[tuple[float, float, float]] = []
        self.subscriptions = [
            self.node.create_subscription(Twist, "/he/final_cmd_vel", self._on_final, 100),
            self.node.create_subscription(
                MotorsState, "/ros_robot_controller/set_motor", self._on_motor, 100
            ),
            self.node.create_subscription(
                SetPWMServoState,
                "/ros_robot_controller/pwm_servo/set_state",
                self._on_servo,
                100,
            ),
            self.node.create_subscription(Odometry, "/odom_raw", self._on_odom, 100),
        ]
        self.publisher = self.node.create_publisher(Twist, "/he/nav_cmd_vel", 1)
        self.stop_event = threading.Event()
        self.spin_thread = threading.Thread(target=self._spin, daemon=True)
        self.spin_thread.start()

    def _on_final(self, message: Twist) -> None:
        self.final_cmd.append((time.monotonic(), message.linear.x, message.angular.z))

    def _on_motor(self, message: MotorsState) -> None:
        self.motor.append((time.monotonic(), {state.id: state.rps for state in message.data}))

    def _on_servo(self, message: SetPWMServoState) -> None:
        for state in message.state:
            if 1 in state.id:
                self.servo.append((time.monotonic(), state.position[state.id.index(1)]))

    def _on_odom(self, message: Odometry) -> None:
        self.odom.append(
            (time.monotonic(), message.twist.twist.linear.x, message.twist.twist.angular.z)
        )

    def _spin(self) -> None:
        while not self.stop_event.is_set():
            rclpy.spin_once(self.node, timeout_sec=0.02)

    def wait_for_graph(self) -> None:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if (
                self.node.count_publishers("/he/nav_cmd_vel") == 1
                and self.node.count_subscribers("/he/nav_cmd_vel") == 1
                and self.node.count_publishers("/ros_robot_controller/set_motor") == 1
                and self.node.count_publishers("/ros_robot_controller/pwm_servo/set_state") == 1
            ):
                time.sleep(0.5)
                return
            time.sleep(0.05)
        raise RuntimeError("ROS endpoint discovery failed")

    def publish(self, linear_x: float, angular_z: float) -> float:
        message = Twist()
        message.linear.x = linear_x
        message.angular.z = angular_z
        stamp = time.monotonic()
        self.publisher.publish(message)
        return stamp

    def publish_for(self, linear_x: float, angular_z: float, duration_s: float) -> tuple[float, float]:
        first = 0.0
        last = 0.0
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            stamp = self.publish(linear_x, angular_z)
            if first == 0.0:
                first = stamp
            last = stamp
            time.sleep(1.0 / PUBLISH_HZ)
        return first, last

    def close(self) -> None:
        for _ in range(5):
            self.publish(0.0, 0.0)
            time.sleep(1.0 / PUBLISH_HZ)
        self.stop_event.set()
        self.spin_thread.join(timeout=2.0)
        self.node.destroy_publisher(self.publisher)
        for subscription in self.subscriptions:
            self.node.destroy_subscription(subscription)
        self.node.destroy_node()


def run_trial(probe: Probe, case: dict[str, Any], repeat: int) -> dict[str, Any]:
    probe.publish_for(0.0, 0.0, 0.15)
    expected = expected_output(case["linear_x"], case["angular_z"])
    command_at, last_command_at = probe.publish_for(
        case["linear_x"], case["angular_z"], case.get("active_s", 0.25)
    )

    final_up = first_after(
        probe.final_cmd,
        command_at,
        lambda sample: math.isclose(sample[1], case["linear_x"], abs_tol=1e-15)
        and math.isclose(sample[2], case["angular_z"], abs_tol=1e-15),
    )
    motor_up = first_after(
        probe.motor,
        command_at,
        lambda sample: all(
            math.isclose(sample[1].get(key, math.nan), value, abs_tol=1e-12)
            for key, value in expected["motor_rps"].items()
        ),
    )
    servo_up = first_after(
        probe.servo, command_at, lambda sample: sample[1] == expected["pwm"]
    )
    odom_up = first_after(
        probe.odom,
        command_at,
        lambda sample: math.isclose(sample[1], expected["linear_x"], abs_tol=1e-15)
        and math.isclose(sample[2], expected["angular_z"], abs_tol=1e-15),
    )

    if case["stop_mode"] == "explicit":
        stop_at, _ = probe.publish_for(0.0, 0.0, 0.20)
    else:
        stop_at = last_command_at
        time.sleep(0.35)

    final_down = optional_first_after(
        probe.final_cmd,
        stop_at,
        lambda sample: abs(sample[1]) < 1e-9 and abs(sample[2]) < 1e-9,
    )
    if case["stop_mode"] == "explicit" and final_down is None:
        raise RuntimeError("explicit zero did not reach /he/final_cmd_vel")
    motor_down = first_after(
        probe.motor,
        stop_at,
        lambda sample: all(abs(value) < 1e-9 for value in sample[1].values()),
    )
    servo_down = first_after(probe.servo, stop_at, lambda sample: sample[1] == 1500)
    odom_down = first_after(
        probe.odom,
        stop_at,
        lambda sample: abs(sample[1]) < 1e-9 and abs(sample[2]) < 1e-9,
    )

    if case["stop_mode"] == "timeout":
        probe.publish_for(0.0, 0.0, 0.20)

    actual_motor = motor_up[1]
    return {
        "case": case["name"],
        "repeat": repeat,
        "stop_mode": case["stop_mode"],
        "input": {"linear_x": case["linear_x"], "angular_z": case["angular_z"]},
        "expected": expected,
        "observed": {
            "final_cmd": {"linear_x": final_up[1], "angular_z": final_up[2]},
            "motor_rps": actual_motor,
            "pwm": servo_up[1],
            "odom_command": {"linear_x": odom_up[1], "angular_z": odom_up[2]},
        },
        "latency_s": {
            "final_up": final_up[0] - command_at,
            "motor_up": motor_up[0] - command_at,
            "servo_up": servo_up[0] - command_at,
            "odom_up": odom_up[0] - command_at,
            "final_down": None if final_down is None else final_down[0] - stop_at,
            "motor_down": motor_down[0] - stop_at,
            "servo_down": servo_down[0] - stop_at,
            "odom_down": odom_down[0] - stop_at,
        },
        "error": {
            "motor_rps_max_abs": max(
                abs(actual_motor[key] - expected["motor_rps"][key]) for key in actual_motor
            ),
            "pwm_abs": abs(servo_up[1] - expected["pwm"]),
            "odom_linear_abs": abs(odom_up[1] - expected["linear_x"]),
            "odom_angular_abs": abs(odom_up[2] - expected["angular_z"]),
        },
    }


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for speed in (0.001, 0.003, 0.005, 0.01, 0.03, 0.05, 0.08, 0.10, 0.15):
        cases.append(
            {
                "name": f"speed_forward_{speed:.3f}",
                "linear_x": speed,
                "angular_z": 0.0,
                "stop_mode": "explicit",
            }
        )
    for speed in (-0.001, -0.01, -0.05, -0.10, -0.15):
        cases.append(
            {
                "name": f"speed_reverse_{abs(speed):.3f}",
                "linear_x": speed,
                "angular_z": 0.0,
                "stop_mode": "explicit",
            }
        )
    for angular in (0.02, 0.05, 0.10, 0.20, 0.30, 0.50):
        for sign, direction in ((1.0, "left"), (-1.0, "right")):
            cases.append(
                {
                    "name": f"steer_{direction}_{angular:.2f}",
                    "linear_x": 0.05,
                    "angular_z": sign * angular,
                    "stop_mode": "explicit",
                }
            )
    for index in range(5):
        cases.append(
            {
                "name": f"watchdog_stop_{index + 1}",
                "linear_x": 0.03,
                "angular_z": 0.10,
                "stop_mode": "timeout",
            }
        )
    return cases


def build_limit_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = [
        {
            "name": "speed_zero",
            "linear_x": 0.0,
            "angular_z": 0.0,
            "stop_mode": "explicit",
        }
    ]
    speed_magnitudes = (
        1e-10,
        1e-9,
        5e-9,
        9e-9,
        1e-8,
        1.1e-8,
        1e-7,
        1e-6,
        1e-5,
        1e-4,
        1e-3,
        0.099999,
        0.10,
        0.100001,
        0.15,
        0.50,
    )
    for speed in speed_magnitudes:
        for sign, direction in ((1.0, "forward"), (-1.0, "reverse")):
            cases.append(
                {
                    "name": f"speed_limit_{direction}_{speed:.10g}",
                    "linear_x": sign * speed,
                    "angular_z": 0.0,
                    "stop_mode": "explicit",
                }
            )

    steering_magnitudes = (
        1e-10,
        1e-9,
        5e-9,
        9e-9,
        1e-8,
        1.1e-8,
        1e-7,
        1e-6,
        1e-5,
        1e-4,
        0.00040,
        0.00044,
        0.00045,
        0.001,
        0.190,
        0.191,
        0.30,
        0.300001,
        0.50,
    )
    cases.append(
        {
            "name": "steering_zero",
            "linear_x": 0.05,
            "angular_z": 0.0,
            "stop_mode": "explicit",
        }
    )
    for angular in steering_magnitudes:
        for sign, direction in ((1.0, "left"), (-1.0, "right")):
            cases.append(
                {
                    "name": f"steering_limit_{direction}_{angular:.10g}",
                    "linear_x": 0.05,
                    "angular_z": sign * angular,
                    "stop_mode": "explicit",
                }
            )
    for sign, direction in ((1.0, "left"), (-1.0, "right")):
        cases.append(
            {
                "name": f"steering_at_zero_speed_{direction}",
                "linear_x": 0.0,
                "angular_z": sign * 0.30,
                "stop_mode": "explicit",
            }
        )
    return cases


def summarize(trials: list[dict[str, Any]]) -> dict[str, Any]:
    latency_names = trials[0]["latency_s"].keys()
    latency = {}
    for name in latency_names:
        values = [
            trial["latency_s"][name]
            for trial in trials
            if trial["latency_s"][name] is not None
        ]
        latency[name] = stats_ms(values) if values else None
    timeout_trials = [trial for trial in trials if trial["stop_mode"] == "timeout"]
    explicit_trials = [trial for trial in trials if trial["stop_mode"] == "explicit"]
    return {
        "trial_count": len(trials),
        "latency_all": latency,
        "explicit_motor_down": (
            stats_ms([trial["latency_s"]["motor_down"] for trial in explicit_trials])
            if explicit_trials
            else None
        ),
        "timeout_motor_down": (
            stats_ms([trial["latency_s"]["motor_down"] for trial in timeout_trials])
            if timeout_trials
            else None
        ),
        "max_error": {
            key: max(trial["error"][key] for trial in trials)
            for key in trials[0]["error"]
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-lifted", action="store_true")
    parser.add_argument(
        "--suite",
        choices=("characterization", "limits"),
        default="characterization",
    )
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    if not args.confirm_lifted:
        raise RuntimeError("refusing real command characterization without --confirm-lifted")
    if args.repeats < 1:
        raise RuntimeError("--repeats must be positive")

    rclpy.init()
    guard = Node("he_chassis_characterization_guard")
    try:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            rclpy.spin_once(guard, timeout_sec=0.05)
        if guard.count_publishers("/he/nav_cmd_vel") != 0:
            raise RuntimeError("/he/nav_cmd_vel already has a publisher")
        if guard.count_publishers("/controller/cmd_vel") != 0:
            raise RuntimeError("joystick publisher is active; stop it before this test")
    finally:
        guard.destroy_node()

    probe = Probe()
    trials: list[dict[str, Any]] = []
    try:
        probe.wait_for_graph()
        cases = build_limit_cases() if args.suite == "limits" else build_cases()
        for case in cases:
            repeats = 1 if case["stop_mode"] == "timeout" else args.repeats
            for repeat in range(1, repeats + 1):
                trials.append(run_trial(probe, case, repeat))
        result = {
            "metadata": {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "measurement_scope": "ROS command and actuator-command topics; no physical encoder",
                "suite": args.suite,
                "wheelbase_m": WHEELBASE_M,
                "track_width_m": TRACK_WIDTH_M,
                "wheel_diameter_m": WHEEL_DIAMETER_M,
                "publish_hz": PUBLISH_HZ,
            },
            "summary": summarize(trials),
            "trials": trials,
        }
        args.output_json.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("HE lifted chassis characterization: PASS")
        print(json.dumps(result["summary"], indent=2, sort_keys=True))
        print(f"result={args.output_json}")
    finally:
        probe.close()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
