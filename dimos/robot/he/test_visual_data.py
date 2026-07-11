"""Unit tests for HE visual sensor qualification helpers."""

from pathlib import Path
import tempfile
import types
import unittest

import cv2
import numpy as np

from dimos.robot.he.visual_data import (
    bgr8_array,
    depth_array,
    depth_ir_quality,
    depth_quality,
    depth_temporal_quality,
    mono8_array,
    occupancy_grid_metrics,
    pointcloud_xyz_quality,
    quaternion_distance_degrees,
    stationary_trajectory_metrics,
    timestamp_alignment,
    topic_rate,
    visual_fault_payload,
    write_visual_snapshot,
)


class TestHEVisualData(unittest.TestCase):
    def test_visual_fault_payload_blanks_only_selected_stream(self) -> None:
        payload = bytes([1, 2, 3])
        self.assertEqual(visual_fault_payload(payload, "rgb", "blank-rgb"), bytes(3))
        self.assertEqual(visual_fault_payload(payload, "depth", "blank-rgb"), payload)
        self.assertEqual(visual_fault_payload(payload, "rgb", "blank-both"), bytes(3))
        with self.assertRaises(ValueError):
            visual_fault_payload(payload, "ir", "blank-rgb")

    def test_timestamp_alignment_uses_nearest_samples(self) -> None:
        metrics = timestamp_alignment([1.0, 2.0, 3.0], [0.995, 2.02, 3.005])
        self.assertEqual(metrics["pairs"], 3)
        self.assertEqual(metrics["reference_samples"], 3)
        self.assertAlmostEqual(metrics["absolute_median_ms"], 5.0)
        self.assertEqual(metrics["within_1ms_ratio"], 0.0)
        self.assertAlmostEqual(metrics["within_10ms_ratio"], 2.0 / 3.0)
        self.assertAlmostEqual(topic_rate([0.0, 0.1, 0.2]), 10.0)

    def test_timestamp_alignment_ignores_non_overlapping_edges(self) -> None:
        metrics = timestamp_alignment([0.0, 1.0, 2.0, 3.0], [0.99, 2.01])
        self.assertEqual(metrics["reference_samples"], 4)
        self.assertEqual(metrics["pairs"], 2)
        self.assertAlmostEqual(metrics["absolute_median_ms"], 10.0)

    def test_depth_array_handles_padding(self) -> None:
        rows = np.array([[0, 100, 0xFFFF], [150, 4000, 0xFFFF]], dtype="<u2")
        message = types.SimpleNamespace(
            encoding="mono16",
            width=2,
            height=2,
            step=6,
            is_bigendian=False,
            data=rows.tobytes(),
        )
        np.testing.assert_array_equal(depth_array(message), [[0, 100], [150, 4000]])

    def test_depth_quality_reports_center_and_spatial_grid(self) -> None:
        depth = np.zeros((10, 10), dtype=np.uint16)
        depth[3:7, 3:7] = 1000
        metrics = depth_quality(depth)
        self.assertAlmostEqual(metrics["valid_ratio"], 0.16)
        self.assertAlmostEqual(metrics["center_40_percent_valid_ratio"], 1.0)
        self.assertEqual(metrics["valid_depth_mm_percentiles"]["50"], 1000.0)
        self.assertEqual(len(metrics["grid_3x3_valid_ratio"]), 3)
        self.assertAlmostEqual(metrics["zero_ratio"], 0.84)
        self.assertEqual(metrics["valid_bbox"]["x_min"], 3)
        self.assertEqual(len(metrics["valid_ratio_by_row"]), 10)
        self.assertEqual(len(metrics["valid_ratio_by_column"]), 10)

    def test_depth_quality_classifies_filtered_values(self) -> None:
        metrics = depth_quality(np.array([[0, 149, 150, 4000, 4001, 65535]], dtype=np.uint16))
        self.assertAlmostEqual(metrics["zero_ratio"], 1.0 / 6.0)
        self.assertAlmostEqual(metrics["below_minimum_nonzero_ratio"], 1.0 / 6.0)
        self.assertAlmostEqual(metrics["valid_ratio"], 2.0 / 6.0)
        self.assertAlmostEqual(metrics["above_maximum_ratio"], 2.0 / 6.0)
        self.assertAlmostEqual(metrics["uint16_max_ratio"], 1.0 / 6.0)

    def test_depth_temporal_quality_reports_stable_component(self) -> None:
        first = np.zeros((4, 5), dtype=np.uint16)
        second = np.zeros((4, 5), dtype=np.uint16)
        first[0:2, 0:2] = 1000
        second[0:2, 0:2] = 1000
        second[3, 4] = 1000
        metrics = depth_temporal_quality([first, second], stable_ratio=1.0)
        self.assertAlmostEqual(metrics["always_valid_ratio"], 4.0 / 20.0)
        self.assertAlmostEqual(metrics["intermittent_valid_ratio"], 1.0 / 20.0)
        self.assertEqual(metrics["largest_stable_component"]["pixels"], 4)
        self.assertEqual(metrics["stable_valid_bbox"]["width"], 2)

    def test_depth_ir_quality_and_mono8_padding(self) -> None:
        message = types.SimpleNamespace(
            encoding="mono8", width=2, height=2, step=3, data=bytes([1, 2, 99, 3, 4, 99])
        )
        ir = mono8_array(message)
        np.testing.assert_array_equal(ir, [[1, 2], [3, 4]])
        depth = np.array([[0, 1000], [0, 2000]], dtype=np.uint16)
        metrics = depth_ir_quality(depth, ir)
        self.assertEqual(metrics["valid_depth_pixels"], 2)
        self.assertAlmostEqual(metrics["ir_mean_at_valid_depth"], 3.0)
        self.assertAlmostEqual(metrics["ir_mean_at_invalid_depth"], 2.0)

    def test_bgr8_array_handles_padding(self) -> None:
        message = types.SimpleNamespace(
            encoding="bgr8",
            width=2,
            height=1,
            step=8,
            data=bytes([1, 2, 3, 4, 5, 6, 99, 99]),
        )
        np.testing.assert_array_equal(
            bgr8_array(message), np.array([[[1, 2, 3], [4, 5, 6]]], dtype=np.uint8)
        )

    def test_write_visual_snapshot_preserves_depth_and_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            metadata = write_visual_snapshot(
                directory,
                depth_stamp=10.0,
                depth=np.array([[0, 150], [4000, 4001]], dtype=np.uint16),
                rgb_stamp=10.001,
                rgb=np.zeros((2, 2, 3), dtype=np.uint8),
                ir_stamp=9.998,
                ir=np.ones((2, 2), dtype=np.uint8),
            )
            saved_depth = cv2.imread(str(directory / "depth-mm.png"), cv2.IMREAD_UNCHANGED)
            saved_mask = cv2.imread(str(directory / "valid-mask.png"), cv2.IMREAD_UNCHANGED)
            self.assertEqual(saved_depth.dtype, np.uint16)
            self.assertEqual(saved_mask.tolist(), [[0, 255], [255, 0]])
            self.assertEqual(metadata["valid_ratio"], 0.5)
            self.assertAlmostEqual(metadata["rgb_absolute_offset_ms"], 1.0)

    def test_pointcloud_xyz_quality(self) -> None:
        points = np.array(
            [(0.0, 0.0, 0.0), (1.0, 2.0, 2.0), (np.nan, 0.0, 1.0)], dtype="<f4"
        )
        fields = [
            types.SimpleNamespace(name=name, offset=offset, datatype=7, count=1)
            for name, offset in (("x", 0), ("y", 4), ("z", 8))
        ]
        message = types.SimpleNamespace(
            fields=fields,
            height=1,
            width=3,
            point_step=12,
            row_step=36,
            is_bigendian=False,
            data=points.tobytes(),
        )
        metrics = pointcloud_xyz_quality(message)
        self.assertAlmostEqual(metrics["zero_xyz_ratio"], 1.0 / 3.0)
        self.assertAlmostEqual(metrics["usable_xyz_ratio"], 1.0 / 3.0)
        self.assertAlmostEqual(metrics["nonfinite_xyz_ratio"], 1.0 / 3.0)
        self.assertEqual(metrics["usable_range_m_percentiles"]["50"], 3.0)

    def test_stationary_trajectory_metrics(self) -> None:
        metrics = stationary_trajectory_metrics(
            [10.0, 10.5, 11.0],
            [[0.0, 0.0, 0.0], [0.01, 0.0, 0.0], [0.0, 0.02, 0.0]],
            [[0.0, 0.0, 0.0, 1.0]] * 3,
            [0.01, 0.02, 0.03],
        )
        self.assertEqual(metrics["samples"], 3)
        self.assertEqual(metrics["output_rate_hz"], 2.0)
        self.assertAlmostEqual(metrics["final_position_drift_m"], 0.02)
        self.assertAlmostEqual(metrics["max_rotation_drift_deg"], 0.0)
        self.assertAlmostEqual(metrics["latency_median_ms"], 20.0)

    def test_quaternion_distance_uses_shortest_rotation(self) -> None:
        self.assertAlmostEqual(
            quaternion_distance_degrees(
                np.array([0.0, 0.0, 0.0, 1.0]),
                np.array([0.0, 0.0, np.sin(np.pi / 4), np.cos(np.pi / 4)]),
            ),
            90.0,
        )

    def test_occupancy_grid_metrics(self) -> None:
        metrics = occupancy_grid_metrics([-1, 0, 49, 50, 100, -1], 3, 2, 0.1)
        self.assertEqual(metrics["unknown_cells"], 2)
        self.assertEqual(metrics["free_cells"], 1)
        self.assertEqual(metrics["occupied_cells"], 2)
        self.assertAlmostEqual(metrics["known_ratio"], 4.0 / 6.0)
        self.assertAlmostEqual(metrics["occupied_ratio_of_known"], 0.5)


if __name__ == "__main__":
    unittest.main()
