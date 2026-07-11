"""Unit tests for Aurora-to-DimOS message conversion."""

from pathlib import Path
import types
import unittest

import numpy as np

from dimos.msgs.sensor_msgs.Image import ImageFormat
from dimos.robot.he.blueprints import he_sense_headless
from dimos.robot.he.sensors import HESensorBridge, HESensorBridgeConfig
from dimos.visualization.rerun.bridge import RerunBridgeModule


def header(frame_id: str = "camera") -> types.SimpleNamespace:
    return types.SimpleNamespace(
        frame_id=frame_id,
        stamp=types.SimpleNamespace(sec=12, nanosec=500_000_000),
    )


class TestHESensorBridge(unittest.TestCase):
    def test_headless_blueprint_keeps_bounded_full_sensor_surface(self) -> None:
        atoms = {atom.module: atom for atom in he_sense_headless.blueprints}

        self.assertEqual(set(atoms), {HESensorBridge, RerunBridgeModule})
        self.assertEqual(atoms[HESensorBridge].kwargs, {})
        sensor_config = HESensorBridgeConfig(**atoms[HESensorBridge].kwargs)
        self.assertTrue(sensor_config.enable_color_image)
        self.assertTrue(sensor_config.enable_depth_image)
        self.assertTrue(sensor_config.enable_ir_image)
        self.assertTrue(sensor_config.enable_pointcloud)
        self.assertTrue(sensor_config.enable_camera_info)
        self.assertEqual(
            atoms[RerunBridgeModule].kwargs,
            {
                "rerun_open": "none",
                "memory_limit": "128MB",
                "latest_only_entities": [
                    "world/color_image",
                    "world/depth_image",
                    "world/ir_image",
                    "world/pointcloud",
                    "world/camera_info",
                    "world/depth_camera_info",
                    "world/odom",
                    "world/imu",
                ],
            },
        )

    def test_all_aurora_modalities_are_enabled_by_default(self) -> None:
        bridge = HESensorBridge()

        self.assertTrue(bridge.config.enable_color_image)
        self.assertTrue(bridge.config.enable_depth_image)
        self.assertTrue(bridge.config.enable_ir_image)
        self.assertTrue(bridge.config.enable_pointcloud)
        self.assertTrue(bridge.config.enable_camera_info)
        self.assertEqual(bridge.config.pointcloud_topic, "/he/aurora/points2_sampled")
        self.assertEqual(bridge.config.pointcloud_max_hz, 1.3)
        self.assertFalse(hasattr(bridge.config, "scan_topic"))

    def test_pointcloud_is_prethrottled_as_serialized_data(self) -> None:
        deployment = Path(__file__).parent / "deployment"
        unit = (deployment / "he-pointcloud-throttle.service").read_text()
        readonly_gate = (deployment / "verify-he-readonly.sh").read_text()

        self.assertIn("/opt/ros/humble/lib/topic_tools/throttle messages", unit)
        self.assertIn("/aurora/points2 1.2 /he/aurora/points2_sampled", unit)
        self.assertIn("MemoryMax=256M", unit)
        self.assertIn("Node name: he_pointcloud_throttle", readonly_gate)
        self.assertIn("Node name: dimos_he_sensors", readonly_gate)

    def test_vendor_package_is_derived_evidence_only(self) -> None:
        repo_root = Path(__file__).parents[3]
        script = (Path(__file__).parent / "deployment" / "build-he-aurora-vendor-package.sh").read_text()
        request = (repo_root / "docs/he/aurora930-vendor-support-request.md").read_text()

        self.assertIn("2026-07-12_0213_he-aurora-sdk-probe.json", script)
        self.assertIn("2026-07-12_0631_native-throttle-raw-timing.json", script)
        self.assertIn("refusing to package image, recording or rosbag payload", script)
        self.assertNotIn("rgb.png", script)
        self.assertNotIn("depth-mm.png", script)
        self.assertIn("The device serial is intentionally omitted", request)
        self.assertIn("Questions Requiring Vendor Answers", request)

    def test_bgr8_image_preserves_shape_padding_and_timestamp(self) -> None:
        rows = np.array(
            [[1, 2, 3, 4, 5, 6, 99, 99], [7, 8, 9, 10, 11, 12, 99, 99]],
            dtype=np.uint8,
        )
        message = types.SimpleNamespace(
            encoding="bgr8",
            width=2,
            height=2,
            step=8,
            is_bigendian=False,
            data=rows.tobytes(),
            header=header("rgb_camera_link"),
        )

        image = HESensorBridge._image_from_ros(message)

        self.assertEqual(image.format, ImageFormat.BGR)
        self.assertEqual(image.shape, (2, 2, 3))
        np.testing.assert_array_equal(image.data.reshape(2, 6), rows[:, :6])
        self.assertEqual(image.frame_id, "rgb_camera_link")
        self.assertEqual(image.ts, 12.5)

    def test_mono16_depth_preserves_uint16_values(self) -> None:
        values = np.array([[0, 500], [1000, 4000]], dtype="<u2")
        message = types.SimpleNamespace(
            encoding="mono16",
            width=2,
            height=2,
            step=4,
            is_bigendian=False,
            data=values.tobytes(),
            header=header("depth_camera_link"),
        )

        image = HESensorBridge._image_from_ros(message)

        self.assertEqual(image.format, ImageFormat.DEPTH16)
        self.assertEqual(image.dtype, np.dtype(np.uint16))
        np.testing.assert_array_equal(image.data, values)

    def test_camera_info_preserves_calibration_and_roi(self) -> None:
        roi = types.SimpleNamespace(
            x_offset=1,
            y_offset=2,
            height=300,
            width=500,
            do_rectify=True,
        )
        message = types.SimpleNamespace(
            height=400,
            width=640,
            distortion_model="plumb_bob",
            d=[0.1] * 5,
            k=[1.0] * 9,
            r=[2.0] * 9,
            p=[3.0] * 12,
            binning_x=0,
            binning_y=0,
            roi=roi,
            header=header("depth_camera_link"),
        )

        result = HESensorBridge._camera_info_from_ros(message)

        self.assertEqual(result.frame_id, "depth_camera_link")
        self.assertEqual(result.D, message.d)
        self.assertEqual(result.K, message.k)
        self.assertEqual(result.roi_x_offset, 1)
        self.assertTrue(result.roi_do_rectify)


if __name__ == "__main__":
    unittest.main()
