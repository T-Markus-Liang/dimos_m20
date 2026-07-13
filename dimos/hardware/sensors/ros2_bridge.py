"""Optional ROS 2 sensor inputs converted to DimOS-native streams."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import threading
import time
from typing import Any

import numpy as np
from pydantic import Field, model_validator

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


def depth_health_metrics(depth: np.ndarray[Any, np.dtype[Any]]) -> dict[str, float]:
    if depth.ndim != 2 or depth.size == 0:
        raise ValueError("depth image must be a non-empty 2D array")
    valid = np.isfinite(depth) & (depth > 0)
    height, width = valid.shape
    y0, y1 = int(height * 0.3), max(int(height * 0.7), int(height * 0.3) + 1)
    x0, x1 = int(width * 0.3), max(int(width * 0.7), int(width * 0.3) + 1)
    bottom = valid[(height * 2) // 3 :, :]
    return {
        "valid_ratio": float(valid.mean()),
        "center_40_percent_valid_ratio": float(valid[y0:y1, x0:x1].mean()),
        "bottom_third_valid_ratio": float(bottom.mean()),
    }


class ROS2SensorBridgeConfig(ModuleConfig):
    ros_node_name: str = "dimos_ros2_sensors"
    enable_odom: bool = False
    odom_topic: str = ""
    odom_max_hz: float = Field(default=0.0, ge=0.0)
    enable_imu: bool = False
    imu_topic: str = ""
    imu_max_hz: float = Field(default=0.0, ge=0.0)
    enable_color_image: bool = False
    color_image_topic: str = ""
    color_image_max_hz: float = Field(default=0.0, ge=0.0)
    enable_depth_image: bool = False
    depth_image_topic: str = ""
    depth_image_max_hz: float = Field(default=0.0, ge=0.0)
    enable_ir_image: bool = False
    ir_image_topic: str = ""
    ir_image_max_hz: float = Field(default=0.0, ge=0.0)
    enable_pointcloud: bool = False
    pointcloud_topic: str = ""
    pointcloud_max_hz: float = Field(default=0.0, ge=0.0)
    enable_camera_info: bool = False
    camera_info_topic: str = ""
    camera_info_max_hz: float = Field(default=0.0, ge=0.0)
    enable_depth_camera_info: bool = False
    depth_camera_info_topic: str = ""
    depth_camera_info_max_hz: float = Field(default=0.0, ge=0.0)
    pointcloud_stride: int = Field(default=8, ge=1)

    @model_validator(mode="after")
    def validate_enabled_channels(self) -> ROS2SensorBridgeConfig:
        channels = (
            (self.enable_odom, self.odom_topic, self.odom_max_hz),
            (self.enable_imu, self.imu_topic, self.imu_max_hz),
            (self.enable_color_image, self.color_image_topic, self.color_image_max_hz),
            (self.enable_depth_image, self.depth_image_topic, self.depth_image_max_hz),
            (self.enable_ir_image, self.ir_image_topic, self.ir_image_max_hz),
            (self.enable_pointcloud, self.pointcloud_topic, self.pointcloud_max_hz),
            (self.enable_camera_info, self.camera_info_topic, self.camera_info_max_hz),
            (
                self.enable_depth_camera_info,
                self.depth_camera_info_topic,
                self.depth_camera_info_max_hz,
            ),
        )
        if any(enabled and (not topic.startswith("/") or max_hz <= 0.0) for enabled, topic, max_hz in channels):
            raise ValueError("enabled ROS sensor channels require an absolute topic and max_hz > 0")
        return self


class ROS2SensorBridge(Module):
    """Bridge explicitly enabled standard ROS 2 sensor topics into DimOS."""

    dedicated_worker = True
    config: ROS2SensorBridgeConfig
    color_image: Out[Image]
    depth_image: Out[Image]
    depth_quality: Out[dict]
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
        if not self._has_enabled_channels():
            logger.info("All ROS sensor inputs disabled; no ROS node created")
            yield
            return
        self._start_ros_subscriptions()
        try:
            yield
        finally:
            self._stop_ros_subscriptions()

    def _has_enabled_channels(self) -> bool:
        return any(
            (
                self.config.enable_odom,
                self.config.enable_imu,
                self.config.enable_color_image,
                self.config.enable_depth_image,
                self.config.enable_ir_image,
                self.config.enable_pointcloud,
                self.config.enable_camera_info,
                self.config.enable_depth_camera_info,
            )
        )

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
            raise RuntimeError("ROS2SensorBridge requires ROS 2 Python packages") from exc

        if not rclpy.ok():
            rclpy.init(args=None)
        self._node = Node(self.config.ros_node_name)
        subscriptions = (
            (self.config.enable_odom, RosOdometry, self.config.odom_topic, self._on_odom),
            (self.config.enable_imu, RosImu, self.config.imu_topic, self._on_imu),
            (
                self.config.enable_color_image,
                RosImage,
                self.config.color_image_topic,
                self._on_color_image,
            ),
            (
                self.config.enable_depth_image,
                RosImage,
                self.config.depth_image_topic,
                self._on_depth_image,
            ),
            (self.config.enable_ir_image, RosImage, self.config.ir_image_topic, self._on_ir_image),
            (
                self.config.enable_pointcloud,
                RosPointCloud2,
                self.config.pointcloud_topic,
                self._on_pointcloud,
            ),
            (
                self.config.enable_camera_info,
                RosCameraInfo,
                self.config.camera_info_topic,
                self._on_camera_info,
            ),
            (
                self.config.enable_depth_camera_info,
                RosCameraInfo,
                self.config.depth_camera_info_topic,
                self._on_depth_camera_info,
            ),
        )
        for enabled, msg_type, topic, callback in subscriptions:
            if enabled:
                self._node.create_subscription(msg_type, topic, callback, qos_profile_sensor_data)
        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(
            target=self._spin_ros, name=f"{self.config.ros_node_name}-spin", daemon=True
        )
        self._spin_thread.start()

    def _spin_ros(self) -> None:
        try:
            if self._executor is not None:
                self._executor.spin()
        except Exception:
            logger.exception("ROS 2 sensor executor stopped unexpectedly")

    def _stop_ros_subscriptions(self) -> None:
        if self._executor is not None:
            self._executor.shutdown()
            self._executor = None
        if self._spin_thread is not None:
            self._spin_thread.join(timeout=2.0)
            if self._spin_thread.is_alive():
                logger.warning("ROS 2 sensor executor did not stop within 2s")
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

    @staticmethod
    def _image_from_ros(msg: Any) -> Image:
        formats: dict[str, tuple[np.dtype[Any], int, ImageFormat]] = {
            "bgr8": (np.dtype(np.uint8), 3, ImageFormat.BGR),
            "rgb8": (np.dtype(np.uint8), 3, ImageFormat.RGB),
            "mono8": (np.dtype(np.uint8), 1, ImageFormat.GRAY),
            "mono16": (np.dtype(np.uint16), 1, ImageFormat.DEPTH16),
            "16uc1": (np.dtype(np.uint16), 1, ImageFormat.DEPTH16),
        }
        encoding = msg.encoding.lower()
        if encoding not in formats:
            raise ValueError(f"unsupported ROS image encoding: {msg.encoding}")
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
            wire_dtype = dtype.newbyteorder(">" if msg.is_bigendian else "<")
            image = np.frombuffer(np.ascontiguousarray(rows).tobytes(), dtype=wire_dtype).reshape(
                msg.height, msg.width
            )
            image = image.astype(dtype, copy=False)
        return Image.from_numpy(
            image,
            format=image_format,
            frame_id=msg.header.frame_id,
            ts=ROS2SensorBridge._timestamp(msg.header),
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
            ts=ROS2SensorBridge._timestamp(msg.header),
        )
        result.roi_x_offset = msg.roi.x_offset
        result.roi_y_offset = msg.roi.y_offset
        result.roi_height = msg.roi.height
        result.roi_width = msg.roi.width
        result.roi_do_rectify = msg.roi.do_rectify
        return result

    def _publish_image(self, stream: str, max_hz: float, port: Out[Image], msg: Any) -> Image | None:
        if not self._allowed(stream, max_hz):
            return None
        try:
            image = self._image_from_ros(msg)
        except ValueError as exc:
            logger.warning("Dropping invalid ROS %s frame: %s", stream, exc)
            return None
        port.publish(image)
        return image

    def _on_color_image(self, msg: Any) -> None:
        self._publish_image("color_image", self.config.color_image_max_hz, self.color_image, msg)

    def _on_depth_image(self, msg: Any) -> None:
        image = self._publish_image(
            "depth_image", self.config.depth_image_max_hz, self.depth_image, msg
        )
        if image is not None:
            self.depth_quality.publish({"stamp": image.ts, **depth_health_metrics(image.data)})

    def _on_ir_image(self, msg: Any) -> None:
        self._publish_image("ir_image", self.config.ir_image_max_hz, self.ir_image, msg)

    def _on_camera_info(self, msg: Any) -> None:
        if self._allowed("camera_info", self.config.camera_info_max_hz):
            self.camera_info.publish(self._camera_info_from_ros(msg))

    def _on_depth_camera_info(self, msg: Any) -> None:
        if self._allowed("depth_camera_info", self.config.depth_camera_info_max_hz):
            self.depth_camera_info.publish(self._camera_info_from_ros(msg))

    def _on_odom(self, msg: Any) -> None:
        if not self._allowed("odom", self.config.odom_max_hz):
            return
        pose, twist = msg.pose.pose, msg.twist.twist
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
                    msg.angular_velocity.x, msg.angular_velocity.y, msg.angular_velocity.z
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

    def _on_pointcloud(self, msg: Any) -> None:
        if not self._allowed("pointcloud", self.config.pointcloud_max_hz):
            return
        try:
            from sensor_msgs_py import point_cloud2
        except ImportError:
            logger.warning("sensor_msgs_py is unavailable; dropping point cloud")
            return
        points = np.asarray(
            point_cloud2.read_points_numpy(
                msg, field_names=("x", "y", "z"), skip_nans=True
            ),
            dtype=np.float32,
        )
        if points.size:
            self.pointcloud.publish(
                PointCloud2.from_numpy(
                    points[:: self.config.pointcloud_stride],
                    frame_id=msg.header.frame_id,
                    timestamp=self._timestamp(msg.header),
                )
            )
