"""Tests for bounded HE IMU diagnostic helpers."""

import json
import math
import unittest

import numpy as np

from dimos.robot.he.imu_data import static_vector_stability, summarize_imu_samples


class TestHEImuData(unittest.TestCase):
    def test_reports_zero_raw_orientation_and_sensor_statistics(self) -> None:
        metrics = summarize_imu_samples(
            stamps=[1.0, 1.02, 1.04],
            quaternions=[[0.0, 0.0, 0.0, 0.0]] * 3,
            gyroscopes=[[0.01, 0.0, 0.0]] * 3,
            accelerations=[[0.0, 0.0, 9.81]] * 3,
            orientation_covariances=[[0.0] * 9] * 3,
            frame_ids={"imu_link"},
        )
        self.assertAlmostEqual(metrics["rate_hz"], 50.0)
        self.assertEqual(metrics["orientation"]["zero_norm_count"], 3)
        self.assertIsNone(metrics["orientation"]["final_rotation_from_first_deg"])
        self.assertEqual(metrics["orientation_covariance"]["all_zero_count"], 3)
        self.assertAlmostEqual(metrics["linear_acceleration_m_s2"]["norm_median"], 9.81)

    def test_reports_filtered_orientation_drift(self) -> None:
        yaw_10 = math.radians(10.0) / 2.0
        metrics = summarize_imu_samples(
            stamps=[1.0, 1.1],
            quaternions=[
                [0.0, 0.0, 0.0, 1.0],
                [0.0, 0.0, math.sin(yaw_10), math.cos(yaw_10)],
            ],
            gyroscopes=[[0.0, 0.0, 0.0]] * 2,
            accelerations=[[0.0, 0.0, 9.81]] * 2,
            orientation_covariances=[[-1.0] + [0.0] * 8] * 2,
            frame_ids={"imu_link"},
        )
        self.assertAlmostEqual(
            metrics["orientation"]["final_rotation_from_first_deg"], 10.0
        )
        self.assertAlmostEqual(metrics["orientation"]["rpy_delta_deg"][2], 10.0)
        self.assertEqual(metrics["orientation_covariance"]["unknown_count"], 2)

    def test_numpy_covariance_counts_are_json_serializable(self) -> None:
        metrics = summarize_imu_samples(
            stamps=[1.0, 1.1],
            quaternions=[[0.0, 0.0, 0.0, 1.0]] * 2,
            gyroscopes=[[0.0, 0.0, 0.0]] * 2,
            accelerations=[[0.0, 0.0, 9.81]] * 2,
            orientation_covariances=[
                [np.float64(0.0)] * 9,
                [np.float64(-1.0)] + [np.float64(0.0)] * 8,
            ],
            frame_ids={"imu_link"},
        )
        json.dumps(metrics)

    def test_static_stability_reports_windows_and_allan_deviation(self) -> None:
        stamps = [index * 0.1 for index in range(40)]
        vectors = [[1.0, 2.0, 3.0]] * 20 + [[1.2, 2.0, 3.0]] * 20
        metrics = static_vector_stability(
            stamps,
            vectors,
            window_seconds=1.0,
            cluster_seconds=(0.1, 0.5, 1.0),
        )
        self.assertEqual(metrics["complete_windows"], 4)
        self.assertAlmostEqual(metrics["window_mean_span"][0], 0.2)
        self.assertEqual(metrics["window_mean_span"][1:], [0.0, 0.0])
        self.assertEqual(len(metrics["allan_deviation"]), 3)
        self.assertGreater(metrics["allan_deviation"][-1]["value"][0], 0.0)

    def test_static_stability_rejects_unpaired_or_nonfinite_data(self) -> None:
        with self.assertRaises(ValueError):
            static_vector_stability([0.0, 1.0], [[0.0, 0.0, 0.0]])
        with self.assertRaises(ValueError):
            static_vector_stability(
                [0.0, 1.0],
                [[0.0, 0.0, 0.0], [math.nan, 0.0, 0.0]],
            )
        with self.assertRaises(ValueError):
            static_vector_stability(
                [0.0, 0.0],
                [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            )


if __name__ == "__main__":
    unittest.main()
