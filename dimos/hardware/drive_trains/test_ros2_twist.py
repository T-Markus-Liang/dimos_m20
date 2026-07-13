import time
from unittest.mock import Mock, call, patch

from pydantic import ValidationError
import pytest

from dimos.hardware.drive_trains.ros2_twist import (
    ROS2TwistConnection,
    ROS2TwistConnectionConfig,
)
from dimos.msgs.geometry_msgs.Twist import Twist


@pytest.fixture
def connection_factory():
    connections: list[ROS2TwistConnection] = []

    def create(**config) -> ROS2TwistConnection:
        connection = ROS2TwistConnection(**config)
        connections.append(connection)
        return connection

    yield create
    for connection in connections:
        connection._close_module()


def test_output_is_disabled_by_default() -> None:
    config = ROS2TwistConnectionConfig()
    assert config.enabled is False
    assert config.ros_cmd_vel_topic == ""


def test_enabled_output_requires_absolute_topic() -> None:
    with pytest.raises(ValidationError):
        ROS2TwistConnectionConfig(enabled=True, ros_cmd_vel_topic="cmd_vel")


def test_nonholonomic_command_is_finite_and_bounded(connection_factory) -> None:
    connection = connection_factory(
        ros_cmd_vel_topic="/cmd_vel", max_linear_mps=0.1, max_angular_radps=0.3
    )
    command = Twist(linear=[1.0, 2.0, 3.0], angular=[4.0, 5.0, -2.0])
    bounded = connection._bounded(command)
    assert list(bounded.linear) == [0.1, 0.0, 0.0]
    assert list(bounded.angular) == [0.0, 0.0, -0.3]


def test_holonomic_profile_allows_bounded_lateral_motion(connection_factory) -> None:
    connection = connection_factory(
        ros_cmd_vel_topic="/cmd_vel", allow_lateral=True, max_lateral_mps=0.2
    )
    command = Twist(linear=[0.0, -1.0, 0.0], angular=[0.0, 0.0, 0.0])
    assert connection._bounded(command).linear.y == -0.2


def test_nonfinite_and_stale_commands_are_zero(connection_factory) -> None:
    connection = connection_factory(ros_cmd_vel_topic="/cmd_vel")
    invalid = Twist(
        linear=[float("nan"), 0.0, 0.0], angular=[0.0, 0.0, float("inf")]
    )
    assert connection._bounded(invalid).is_zero()
    connection._latest_command = Twist(
        linear=[0.05, 0.0, 0.0], angular=[0.0, 0.0, 0.1]
    )
    connection._latest_command_at = time.monotonic() - 1.0
    assert connection._fresh_command().is_zero()


def test_shutdown_publishes_three_spaced_zero_commands(connection_factory) -> None:
    connection = connection_factory(ros_cmd_vel_topic="/cmd_vel")
    connection._publisher = object()
    connection._publish = Mock()  # type: ignore[method-assign]
    with patch("dimos.hardware.drive_trains.ros2_twist.time.sleep") as sleep:
        connection._publish_stop()
    assert connection._publish.call_count == 3
    assert all(item.args[0].is_zero() for item in connection._publish.call_args_list)
    assert sleep.call_args_list == [call(0.05), call(0.05)]
