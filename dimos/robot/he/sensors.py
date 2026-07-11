"""ROS 2 sensor bridge for the HE Ackermann robot."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import AsyncGenerator
from typing import Any

import numpy as np
from pydantic import Field

from dimos.core.module import Module, ModuleConfig
from dimos.core.stream import Out
from dimos.msgs.geometry_msgs.Pose import Pose
from dimos.msgs.geometry_msgs.Quaternion import Quaternion
from dimos.msgs.geometry_msgs.Twist import Twist
from dimos.msgs.geometry_msgs.Vector3 import Vector3
from dimos.msgs.nav_msgs.Odometry import Odometry
from dimos.msgs.sensor_msgs.Imu import Imu
from dimos.msgs.sensor_msgs.PointCloud2 import PointCloud2
from dimos.utils.logging_config import setup_logger

logger = setup_logger()


class HESensorBridgeConfig(ModuleConfig):
    ros_node_name: str = "dimos_he_sensors"
    scan_topic: str = "/scan"
    odom_topic: str = "/odom_raw"
    imu_topic: str = "/ros_robot_controller/imu_raw"
    camera_pointcloud_topic: str = "/aurora/points2"
    lidar_max_hz: float = Field(default=10.0, ge=0.0)
    odom_max_hz: float = Field(default=20.0, ge=0.0)
    imu_max_hz: float = Field(default=20.0, ge=0.0)
    enable_camera_pointcloud: bool = False
    camera_pointcloud_max_hz: float = Field(default=1.0, ge=0.0)
    camera_point_stride: int = Field(default=8, ge=1)


class HESensorBridge(Module):
    """Convert HE ROS 2 sensor topics to DimOS-native messages.

    The LD19 scan is converted to a planar PointCloud2 stream. Aurora point
    clouds are deliberately opt-in and downsampled because the raw stream is
    about 58MB/s on this platform.
    """

    dedicated_worker = True

    config: HESensorBridgeConfig
    lidar: Out[PointCloud2]
    camera_pointcloud: Out[PointCloud2]
    odom: Out[Odometry]
    imu: Out[Imu]

    def __init__(self, **config_args: Any) -> None:
        super().__init__(**config_args)
        self._node: Any | None = None
        self._executor: Any | None = None
        self._spin_thread: threading.Thread | None = None
        self._last_published: dict[str, float] = {}

    async def main(self) -> AsyncGenerator[None, None]:
        self._start_ros_subscriptions()
        try:
            yield
        finally:
            self._stop_ros_subscriptions()

    def _start_ros_subscriptions(self) -> None:
        try:
            import rclpy
            from nav_msgs.msg import Odometry as RosOdometry
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.node import Node
            from rclpy.qos import qos_profile_sensor_data
            from sensor_msgs.msg import Imu as RosImu
            from sensor_msgs.msg import LaserScan
            from sensor_msgs.msg import PointCloud2 as RosPointCloud2
        except ImportError as exc:
            raise RuntimeError("HESensorBridge requires ROS 2 Humble Python packages") from exc

        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = Node(self.config.ros_node_name)
        self._node.create_subscription(LaserScan, self.config.scan_topic, self._on_scan, qos_profile_sensor_data)
        self._node.create_subscription(
            RosOdometry, self.config.odom_topic, self._on_odom, qos_profile_sensor_data
        )
        self._node.create_subscription(RosImu, self.config.imu_topic, self._on_imu, qos_profile_sensor_data)
        if self.config.enable_camera_pointcloud:
            self._node.create_subscription(
                RosPointCloud2,
                self.config.camera_pointcloud_topic,
                self._on_camera_pointcloud,
                qos_profile_sensor_data,
            )

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(target=self._spin_ros, daemon=True)
        self._spin_thread.start()
        logger.info(
            "HE ROS bridge started: scan=%s odom=%s imu=%s camera_pointcloud=%s",
            self.config.scan_topic,
            self.config.odom_topic,
            self.config.imu_topic,
            self.config.enable_camera_pointcloud,
        )

    def _spin_ros(self) -> None:
        from rclpy.executors import ExternalShutdownException

        try:
            if self._executor is not None:
                self._executor.spin()
        except ExternalShutdownException:
            # The process-wide ROS context is already stopping.
            pass

    def _stop_ros_subscriptions(self) -> None:
        if self._executor is not None:
            self._executor.shutdown()
            self._executor = None
        if self._spin_thread is not None:
            self._spin_thread.join(timeout=2.0)
            self._spin_thread = None
        if self._node is not None:
            self._node.destroy_node()
            self._node = None

    def _allowed(self, stream: str, max_hz: float) -> bool:
        if max_hz <= 0.0:
            return False
        now = time.monotonic()
        previous = self._last_published.get(stream, 0.0)
        if now - previous < 1.0 / max_hz:
            return False
        self._last_published[stream] = now
        return True

    @staticmethod
    def _timestamp(header: Any) -> float:
        return float(header.stamp.sec) + float(header.stamp.nanosec) / 1_000_000_000.0

    def _on_scan(self, msg: Any) -> None:
        if not self._allowed("lidar", self.config.lidar_max_hz):
            return
        ranges = np.asarray(msg.ranges, dtype=np.float32)
        angles = msg.angle_min + np.arange(ranges.size, dtype=np.float32) * msg.angle_increment
        valid = np.isfinite(ranges)
        valid &= ranges >= msg.range_min
        valid &= ranges <= msg.range_max
        if not np.any(valid):
            return
        selected = ranges[valid]
        selected_angles = angles[valid]
        points = np.column_stack(
            (
                selected * np.cos(selected_angles),
                selected * np.sin(selected_angles),
                np.zeros(selected.size, dtype=np.float32),
            )
        )
        self.lidar.publish(
            PointCloud2.from_numpy(
                points,
                frame_id=msg.header.frame_id or "lidar_frame",
                timestamp=self._timestamp(msg.header),
            )
        )

    def _on_odom(self, msg: Any) -> None:
        if not self._allowed("odom", self.config.odom_max_hz):
            return
        pose = msg.pose.pose
        twist = msg.twist.twist
        self.odom.publish(
            Odometry(
                ts=self._timestamp(msg.header),
                frame_id=msg.header.frame_id,
                child_frame_id=msg.child_frame_id,
                pose=Pose(
                    pose.position.x,
                    pose.position.y,
                    pose.position.z,
                    pose.orientation.x,
                    pose.orientation.y,
                    pose.orientation.z,
                    pose.orientation.w,
                ),
                twist=Twist(
                    linear=[twist.linear.x, twist.linear.y, twist.linear.z],
                    angular=[twist.angular.x, twist.angular.y, twist.angular.z],
                ),
            )
        )

    def _on_imu(self, msg: Any) -> None:
        if not self._allowed("imu", self.config.imu_max_hz):
            return
        self.imu.publish(
            Imu(
                angular_velocity=Vector3(
                    msg.angular_velocity.x,
                    msg.angular_velocity.y,
                    msg.angular_velocity.z,
                ),
                linear_acceleration=Vector3(
                    msg.linear_acceleration.x,
                    msg.linear_acceleration.y,
                    msg.linear_acceleration.z,
                ),
                orientation=Quaternion(
                    msg.orientation.x,
                    msg.orientation.y,
                    msg.orientation.z,
                    msg.orientation.w,
                ),
                orientation_covariance=list(msg.orientation_covariance),
                angular_velocity_covariance=list(msg.angular_velocity_covariance),
                linear_acceleration_covariance=list(msg.linear_acceleration_covariance),
                frame_id=msg.header.frame_id or "imu_link",
                ts=self._timestamp(msg.header),
            )
        )

    def _on_camera_pointcloud(self, msg: Any) -> None:
        if not self._allowed("camera_pointcloud", self.config.camera_pointcloud_max_hz):
            return
        try:
            from sensor_msgs_py import point_cloud2
        except ImportError:
            logger.warning("sensor_msgs_py is unavailable; Aurora point cloud is disabled")
            return
        points = np.asarray(
            list(point_cloud2.read_points(msg, field_names=("x", "y", "z"), skip_nans=True)),
            dtype=np.float32,
        )
        if points.size == 0:
            return
        points = points[:: self.config.camera_point_stride]
        self.camera_pointcloud.publish(
            PointCloud2.from_numpy(
                points,
                frame_id=msg.header.frame_id or "depth_camera_link",
                timestamp=self._timestamp(msg.header),
            )
        )
