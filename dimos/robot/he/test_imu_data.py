"""Tests for bounded HE IMU diagnostic helpers."""

import math
import unittest

from dimos.robot.he.imu_data import summarize_imu_samples


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


if __name__ == "__main__":
    unittest.main()
