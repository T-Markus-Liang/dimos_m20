import types
from unittest.mock import Mock

import numpy as np
from pydantic import ValidationError
import pytest

from dimos.hardware.sensors.ros2_bridge import (
    ROS2SensorBridge,
    ROS2SensorBridgeConfig,
    depth_health_metrics,
)
from dimos.msgs.sensor_msgs.Image import ImageFormat


def header(frame_id: str = "camera") -> types.SimpleNamespace:
    return types.SimpleNamespace(
        frame_id=frame_id,
        stamp=types.SimpleNamespace(sec=12, nanosec=500_000_000),
    )


def test_all_channels_are_disabled_by_default() -> None:
    config = ROS2SensorBridgeConfig()
    assert not any(
        (
            config.enable_odom,
            config.enable_imu,
            config.enable_color_image,
            config.enable_depth_image,
            config.enable_ir_image,
            config.enable_pointcloud,
            config.enable_camera_info,
            config.enable_depth_camera_info,
        )
    )


@pytest.mark.asyncio
async def test_disabled_bridge_does_not_start_ros() -> None:
    bridge = ROS2SensorBridge()
    bridge._start_ros_subscriptions = Mock()  # type: ignore[method-assign]
    main = bridge.main()
    try:
        await anext(main)
        with pytest.raises(StopAsyncIteration):
            await anext(main)
        bridge._start_ros_subscriptions.assert_not_called()
    finally:
        bridge._close_module()


def test_enabled_channel_requires_absolute_topic_and_rate() -> None:
    with pytest.raises(ValidationError):
        ROS2SensorBridgeConfig(enable_imu=True, imu_topic="imu", imu_max_hz=20)


def test_bgr8_preserves_padding_and_timestamp() -> None:
    rows = np.array(
        [[1, 2, 3, 4, 5, 6, 99, 99], [7, 8, 9, 10, 11, 12, 99, 99]], dtype=np.uint8
    )
    message = types.SimpleNamespace(
        encoding="bgr8",
        width=2,
        height=2,
        step=8,
        is_bigendian=False,
        data=rows.tobytes(),
        header=header("rgb"),
    )

    image = ROS2SensorBridge._image_from_ros(message)

    assert image.format == ImageFormat.BGR
    assert image.shape == (2, 2, 3)
    np.testing.assert_array_equal(image.data.reshape(2, 6), rows[:, :6])
    assert image.ts == 12.5


def test_mono16_preserves_values_and_byte_order() -> None:
    values = np.array([[0, 500], [1000, 4000]], dtype=">u2")
    message = types.SimpleNamespace(
        encoding="16UC1",
        width=2,
        height=2,
        step=4,
        is_bigendian=True,
        data=values.tobytes(),
        header=header("depth"),
    )

    image = ROS2SensorBridge._image_from_ros(message)

    assert image.format == ImageFormat.DEPTH16
    np.testing.assert_array_equal(image.data, values.astype(np.uint16))


def test_depth_health_reports_global_center_and_bottom() -> None:
    depth = np.zeros((6, 6), dtype=np.uint16)
    depth[2:4, 2:4] = 1000
    depth[4:, :3] = 1000

    metrics = depth_health_metrics(depth)

    assert metrics["valid_ratio"] == pytest.approx(10 / 36)
    assert metrics["center_40_percent_valid_ratio"] == pytest.approx(4 / 9)
    assert metrics["bottom_third_valid_ratio"] == 0.5
