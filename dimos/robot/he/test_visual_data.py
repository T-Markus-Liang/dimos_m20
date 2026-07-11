"""Unit tests for HE visual sensor qualification helpers."""

import types
import unittest

import numpy as np

from dimos.robot.he.visual_data import depth_array, depth_quality, timestamp_alignment, topic_rate


class TestHEVisualData(unittest.TestCase):
    def test_timestamp_alignment_uses_nearest_samples(self) -> None:
        metrics = timestamp_alignment([1.0, 2.0, 3.0], [0.99, 2.02, 3.01])
        self.assertEqual(metrics["pairs"], 3)
        self.assertAlmostEqual(metrics["absolute_median_ms"], 10.0)
        self.assertAlmostEqual(topic_rate([0.0, 0.1, 0.2]), 10.0)

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


if __name__ == "__main__":
    unittest.main()
