"""Software-only safety tests for the HE chassis command bridge."""

import time
import unittest
from unittest.mock import Mock

from dimos.msgs.geometry_msgs.Twist import Twist
from dimos.robot.he.connection import HEConnection


class TestHEConnectionSafety(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = HEConnection()

    def test_motion_output_is_disabled_by_default(self) -> None:
        self.assertFalse(self.connection.config.enabled)
        self.assertEqual(self.connection.config.ros_cmd_vel_topic, "/he/nav_cmd_vel")

    def test_command_is_clamped_and_lateral_motion_is_removed(self) -> None:
        command = Twist(linear=[1.0, 2.0, 3.0], angular=[4.0, 5.0, -2.0])

        bounded = self.connection._bounded(command)

        self.assertEqual(list(bounded.linear), [0.10, 0.0, 0.0])
        self.assertEqual(list(bounded.angular), [0.0, 0.0, -0.30])

    def test_non_finite_command_is_zeroed(self) -> None:
        command = Twist(linear=[float("nan"), 0.0, 0.0], angular=[0.0, 0.0, float("inf")])

        self.assertTrue(self.connection._bounded(command).is_zero())

    def test_stale_command_is_zeroed(self) -> None:
        self.connection._latest_command = Twist(linear=[0.05, 0.0, 0.0], angular=[0.0, 0.0, 0.1])
        self.connection._latest_command_at = time.monotonic() - 1.0

        self.assertTrue(self.connection._fresh_command().is_zero())

    def test_fresh_command_is_preserved(self) -> None:
        command = Twist(linear=[0.05, 0.0, 0.0], angular=[0.0, 0.0, 0.1])
        self.connection._latest_command = command
        self.connection._latest_command_at = time.monotonic()

        self.assertIs(self.connection._fresh_command(), command)

    def test_shutdown_publishes_three_spaced_zero_commands(self) -> None:
        publish = Mock()
        self.connection._publisher = object()
        self.connection._publish = publish  # type: ignore[method-assign]

        with unittest.mock.patch("dimos.robot.he.connection.time.sleep") as sleep:
            self.connection._publish_stop()

        self.assertEqual(publish.call_count, 3)
        self.assertTrue(all(call.args[0].is_zero() for call in publish.call_args_list))
        self.assertEqual(sleep.call_args_list, [unittest.mock.call(0.05)] * 2)


if __name__ == "__main__":
    unittest.main()
