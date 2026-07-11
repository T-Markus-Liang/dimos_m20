"""Safe DimOS-to-ROS 2 velocity bridge for the HE Ackermann chassis."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import AsyncGenerator
from typing import Any

from pydantic import Field

from dimos.core.module import Module, ModuleConfig
from dimos.core.stream import In
from dimos.msgs.geometry_msgs.Twist import Twist
from dimos.utils.logging_config import setup_logger

logger = setup_logger()


class HEConnectionConfig(ModuleConfig):
    enabled: bool = False
    ros_cmd_vel_topic: str = "/he/nav_cmd_vel"
    ros_node_name: str = "dimos_he_connection"
    max_linear_mps: float = Field(default=0.10, gt=0.0)
    max_angular_radps: float = Field(default=0.30, gt=0.0)
    cmd_rate_hz: float = Field(default=20.0, gt=0.0)
    cmd_timeout_s: float = Field(default=0.20, gt=0.0)


class HEConnection(Module):
    """Publish the final DimOS command to HE through the existing ROS layer.

    The bridge is disabled by default. When explicitly enabled it publishes
    only bounded Ackermann-compatible commands and sends zero velocity whenever
    the DimOS command becomes stale or the module stops.
    """

    dedicated_worker = True

    config: HEConnectionConfig
    cmd_vel: In[Twist]

    def __init__(self, **config_args: Any) -> None:
        super().__init__(**config_args)
        self._node: Any | None = None
        self._publisher: Any | None = None
        self._ros_twist_type: type[Any] | None = None
        self._latest_command = Twist.zero()
        self._latest_command_at = 0.0
        self._publish_task: asyncio.Task[None] | None = None

    async def main(self) -> AsyncGenerator[None, None]:
        if self.config.enabled:
            self._start_ros_publisher()
            self._publish_task = asyncio.create_task(self._publish_loop())
            logger.warning(
                "HE motion output enabled: %s, max_linear=%sm/s, max_angular=%srad/s",
                self.config.ros_cmd_vel_topic,
                self.config.max_linear_mps,
                self.config.max_angular_radps,
            )
        else:
            logger.warning("HE motion output is disabled; no ROS /cmd_vel publisher will be created")

        try:
            yield
        finally:
            if self._publish_task is not None:
                self._publish_task.cancel()
                try:
                    await self._publish_task
                except asyncio.CancelledError:
                    pass
                self._publish_task = None
            self._publish_stop()
            self._destroy_ros_node()

    async def handle_cmd_vel(self, msg: Twist) -> None:
        self._latest_command = self._bounded(msg)
        self._latest_command_at = time.monotonic()

    def _start_ros_publisher(self) -> None:
        try:
            import rclpy
            from geometry_msgs.msg import Twist as RosTwist
            from rclpy.node import Node
        except ImportError as exc:
            raise RuntimeError("HEConnection requires ROS 2 Humble Python packages") from exc

        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = Node(self.config.ros_node_name)
        self._ros_twist_type = RosTwist
        self._publisher = self._node.create_publisher(RosTwist, self.config.ros_cmd_vel_topic, 1)

    async def _publish_loop(self) -> None:
        period_s = 1.0 / self.config.cmd_rate_hz
        while True:
            self._publish(self._fresh_command())
            await asyncio.sleep(period_s)

    def _fresh_command(self) -> Twist:
        if time.monotonic() - self._latest_command_at > self.config.cmd_timeout_s:
            return Twist.zero()
        return self._latest_command

    def _bounded(self, msg: Twist) -> Twist:
        linear_x = self._finite_and_clamp(msg.linear.x, self.config.max_linear_mps)
        angular_z = self._finite_and_clamp(msg.angular.z, self.config.max_angular_radps)
        return Twist(linear=[linear_x, 0.0, 0.0], angular=[0.0, 0.0, angular_z])

    @staticmethod
    def _finite_and_clamp(value: float, limit: float) -> float:
        if not math.isfinite(value):
            return 0.0
        return max(-limit, min(limit, value))

    def _publish(self, command: Twist) -> None:
        if self._publisher is None or self._ros_twist_type is None:
            return
        msg = self._ros_twist_type()
        msg.linear.x = command.linear.x
        msg.angular.z = command.angular.z
        self._publisher.publish(msg)

    def _publish_stop(self) -> None:
        if self._publisher is None:
            return
        interval_s = 1.0 / self.config.cmd_rate_hz
        for index in range(3):
            self._publish(Twist.zero())
            if index < 2:
                time.sleep(interval_s)

    def _destroy_ros_node(self) -> None:
        if self._node is not None:
            self._node.destroy_node()
            self._node = None
        self._publisher = None
        self._ros_twist_type = None
