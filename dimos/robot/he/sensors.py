"""ROS 2 sensor bridge for the HE Ackermann robot."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import threading
import time
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
from dimos.msgs.sensor_msgs.CameraInfo import CameraInfo
from dimos.msgs.sensor_msgs.Image import Image, ImageFormat
from dimos.msgs.sensor_msgs.Imu import Imu
from dimos.msgs.sensor_msgs.PointCloud2 import PointCloud2
from dimos.utils.logging_config import setup_logger

logger = setup_logger()


class HESensorBridgeConfig(ModuleConfig):
    ros_node_name: str = "dimos_he_sensors"
    odom_topic: str = "/odom_raw"
    imu_topic: str = "/ros_robot_controller/imu_raw"
    color_image_topic: str = "/aurora/rgb/image_raw"
    depth_image_topic: str = "/aurora/depth/image_raw"
    ir_image_topic: str = "/aurora/ir/image_raw"
    pointcloud_topic: str = "/he/aurora/points2_sampled"
    camera_info_topic: str = "/aurora/rgb/camera_info"
    depth_camera_info_topic: str = "/aurora/ir/camera_info"
    odom_max_hz: float = Field(default=20.0, ge=0.0)
    imu_max_hz: float = Field(default=20.0, ge=0.0)
    color_image_max_hz: float = Field(default=5.0, ge=0.0)
    depth_image_max_hz: float = Field(default=5.0, ge=0.0)
    ir_image_max_hz: float = Field(default=5.0, ge=0.0)
    pointcloud_max_hz: float = Field(default=1.1, ge=0.0)
    camera_info_max_hz: float = Field(default=1.0, ge=0.0)
    pointcloud_stride: int = Field(default=8, ge=1)
    enable_color_image: bool = True
    enable_depth_image: bool = True
    enable_ir_image: bool = True
    enable_pointcloud: bool = True
    enable_camera_info: bool = True


class HESensorBridge(Module):
    """Convert HE ROS 2 sensor topics to DimOS-native messages.

    All Aurora modalities are enabled by default. Images retain their native
    precision, while the high-bandwidth point cloud is rate-limited and
    downsampled before it enters DimOS.
    """

    dedicated_worker = True

    config: HESensorBridgeConfig
    color_image: Out[Image]
    depth_image: Out[Image]
    ir_image: Out[Image]
    pointcloud: Out[PointCloud2]
    camera_info: Out[CameraInfo]
    depth_camera_info: Out[CameraInfo]
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
            from nav_msgs.msg import Odometry as RosOdometry
            import rclpy
            from rclpy.executors import SingleThreadedExecutor
            from rclpy.node import Node
            from rclpy.qos import qos_profile_sensor_data
            from sensor_msgs.msg import (
                CameraInfo as RosCameraInfo,
                Image as RosImage,
                Imu as RosImu,
                PointCloud2 as RosPointCloud2,
            )
        except ImportError as exc:
            raise RuntimeError("HESensorBridge requires ROS 2 Humble Python packages") from exc

        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = Node(self.config.ros_node_name)
        self._node.create_subscription(
            RosOdometry, self.config.odom_topic, self._on_odom, qos_profile_sensor_data
        )
        self._node.create_subscription(
            RosImu, self.config.imu_topic, self._on_imu, qos_profile_sensor_data
        )
        if self.config.enable_color_image:
            self._node.create_subscription(
                RosImage,
                self.config.color_image_topic,
                self._on_color_image,
                qos_profile_sensor_data,
            )
        if self.config.enable_depth_image:
            self._node.create_subscription(
                RosImage,
                self.config.depth_image_topic,
                self._on_depth_image,
                qos_profile_sensor_data,
            )
        if self.config.enable_ir_image:
            self._node.create_subscription(
                RosImage,
                self.config.ir_image_topic,
                self._on_ir_image,
                qos_profile_sensor_data,
            )
        if self.config.enable_pointcloud:
            self._node.create_subscription(
                RosPointCloud2,
                self.config.pointcloud_topic,
                self._on_pointcloud,
                qos_profile_sensor_data,
            )
        if self.config.enable_camera_info:
            self._node.create_subscription(
                RosCameraInfo,
                self.config.camera_info_topic,
                self._on_camera_info,
                qos_profile_sensor_data,
            )
            self._node.create_subscription(
                RosCameraInfo,
                self.config.depth_camera_info_topic,
                self._on_depth_camera_info,
                qos_profile_sensor_data,
            )

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(target=self._spin_ros, daemon=True)
        self._spin_thread.start()
        logger.info(
            "HE ROS bridge started: odom=%s imu=%s Aurora(rgb=%s depth=%s ir=%s points=%s info=%s)",
            self.config.odom_topic,
            self.config.imu_topic,
            self.config.enable_color_image,
            self.config.enable_depth_image,
            self.config.enable_ir_image,
            self.config.enable_pointcloud,
            self.config.enable_camera_info,
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

    @staticmethod
    def _image_from_ros(msg: Any) -> Image:
        encoding = msg.encoding.lower()
        formats: dict[str, tuple[np.dtype[Any], int, ImageFormat]] = {
            "bgr8": (np.dtype(np.uint8), 3, ImageFormat.BGR),
            "rgb8": (np.dtype(np.uint8), 3, ImageFormat.RGB),
            "mono8": (np.dtype(np.uint8), 1, ImageFormat.GRAY),
            "mono16": (np.dtype(np.uint16), 1, ImageFormat.DEPTH16),
            "16uc1": (np.dtype(np.uint16), 1, ImageFormat.DEPTH16),
        }
        if encoding not in formats:
            raise ValueError(f"unsupported Aurora image encoding: {msg.encoding}")
        dtype, channels, image_format = formats[encoding]
        row_bytes = msg.width * channels * dtype.itemsize
        if msg.step < row_bytes:
            raise ValueError(f"image step {msg.step} is smaller than row payload {row_bytes}")
        raw = np.frombuffer(msg.data, dtype=np.uint8)
        required = msg.height * msg.step
        if raw.size < required:
            raise ValueError(f"image payload has {raw.size} bytes, expected at least {required}")
        rows = raw[:required].reshape(msg.height, msg.step)[:, :row_bytes]
        if dtype.itemsize == 1:
            shape = (msg.height, msg.width, channels) if channels > 1 else (msg.height, msg.width)
            image = np.ascontiguousarray(rows).reshape(shape)
        else:
            byte_order = ">" if msg.is_bigendian else "<"
            wire_dtype = dtype.newbyteorder(byte_order)
            image = np.frombuffer(np.ascontiguousarray(rows).tobytes(), dtype=wire_dtype).reshape(
                msg.height, msg.width
            )
            image = image.astype(dtype, copy=False)
        return Image.from_numpy(
            image,
            format=image_format,
            frame_id=msg.header.frame_id,
            ts=HESensorBridge._timestamp(msg.header),
        )

    @staticmethod
    def _camera_info_from_ros(msg: Any) -> CameraInfo:
        result = CameraInfo(
            height=msg.height,
            width=msg.width,
            distortion_model=msg.distortion_model,
            D=list(msg.d),
            K=list(msg.k),
            R=list(msg.r),
            P=list(msg.p),
            binning_x=msg.binning_x,
            binning_y=msg.binning_y,
            frame_id=msg.header.frame_id,
            ts=HESensorBridge._timestamp(msg.header),
        )
        result.roi_x_offset = msg.roi.x_offset
        result.roi_y_offset = msg.roi.y_offset
        result.roi_height = msg.roi.height
        result.roi_width = msg.roi.width
        result.roi_do_rectify = msg.roi.do_rectify
        return result

    def _publish_image(self, stream: str, max_hz: float, port: Out[Image], msg: Any) -> None:
        if not self._allowed(stream, max_hz):
            return
        try:
            port.publish(self._image_from_ros(msg))
        except ValueError as exc:
            logger.warning("Dropping invalid Aurora %s frame: %s", stream, exc)

    def _on_color_image(self, msg: Any) -> None:
        self._publish_image("color_image", self.config.color_image_max_hz, self.color_image, msg)

    def _on_depth_image(self, msg: Any) -> None:
        self._publish_image("depth_image", self.config.depth_image_max_hz, self.depth_image, msg)

    def _on_ir_image(self, msg: Any) -> None:
        self._publish_image("ir_image", self.config.ir_image_max_hz, self.ir_image, msg)

    def _on_camera_info(self, msg: Any) -> None:
        if self._allowed("camera_info", self.config.camera_info_max_hz):
            self.camera_info.publish(self._camera_info_from_ros(msg))

    def _on_depth_camera_info(self, msg: Any) -> None:
        if self._allowed("depth_camera_info", self.config.camera_info_max_hz):
            self.depth_camera_info.publish(self._camera_info_from_ros(msg))

    def _on_pointcloud(self, msg: Any) -> None:
        if not self._allowed("pointcloud", self.config.pointcloud_max_hz):
            return
        try:
            from sensor_msgs_py import point_cloud2
        except ImportError:
            logger.warning("sensor_msgs_py is unavailable; dropping Aurora point cloud")
            return
        points = np.asarray(
            point_cloud2.read_points_numpy(
                msg,
                field_names=("x", "y", "z"),
                skip_nans=True,
            ),
            dtype=np.float32,
        )
        if points.size == 0:
            return
        points = points[:: self.config.pointcloud_stride]
        self.pointcloud.publish(
            PointCloud2.from_numpy(
                points,
                frame_id=msg.header.frame_id or "depth_camera_link",
                timestamp=self._timestamp(msg.header),
            )
        )
