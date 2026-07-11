"""Tests for the HE visual SLAM shadow adapters and health gates."""

from __future__ import annotations

import types
import unittest

import numpy as np

from dimos.msgs.nav_msgs.OccupancyGrid import OccupancyGrid
from dimos.msgs.nav_msgs.Odometry import Odometry
from dimos.robot.he.blueprints import he_visual_slam_shadow
from dimos.robot.he.visual_slam import (
    HELocalizationHealth,
    HEVisualMapAdapter,
    HEVisualSlamBridge,
)


def header(stamp: float = 100.0, frame_id: str = "he_map") -> types.SimpleNamespace:
    seconds = int(stamp)
    return types.SimpleNamespace(
        frame_id=frame_id,
        stamp=types.SimpleNamespace(sec=seconds, nanosec=int((stamp - seconds) * 1e9)),
    )


def pose(x: float = 0.0, quaternion: tuple[float, float, float, float] = (0, 0, 0, 1)):
    return types.SimpleNamespace(
        position=types.SimpleNamespace(x=x, y=0.0, z=0.0),
        orientation=types.SimpleNamespace(
            x=quaternion[0], y=quaternion[1], z=quaternion[2], w=quaternion[3]
        ),
    )


def ros_odom(stamp: float = 100.0):
    vector = types.SimpleNamespace(x=0.0, y=0.0, z=0.0)
    return types.SimpleNamespace(
        header=header(stamp, "he_visual_odom"),
        child_frame_id="base_link",
        pose=types.SimpleNamespace(pose=pose(), covariance=[0.0] * 36),
        twist=types.SimpleNamespace(
            twist=types.SimpleNamespace(linear=vector, angular=vector), covariance=[0.0] * 36
        ),
    )


def ros_map(data: list[int], width: int, height: int, stamp: float = 100.0):
    return types.SimpleNamespace(
        header=header(stamp),
        info=types.SimpleNamespace(width=width, height=height, resolution=0.05, origin=pose()),
        data=data,
    )


class TestHEVisualSlamBridge(unittest.TestCase):
    def test_odometry_conversion_preserves_frames_covariance_and_stamp(self) -> None:
        result = HEVisualSlamBridge.odometry_from_ros(ros_odom())
        self.assertEqual(result.frame_id, "he_visual_odom")
        self.assertEqual(result.child_frame_id, "base_link")
        self.assertEqual(result.ts, 100.0)
        self.assertEqual(len(result.pose.covariance), 36)

    def test_occupancy_conversion_preserves_unknown_cells(self) -> None:
        result = HEVisualSlamBridge.occupancy_from_ros(ros_map([-1, 0, 50, 100], 2, 2))
        np.testing.assert_array_equal(result.grid, [[-1, 0], [50, 100]])
        self.assertEqual(result.frame_id, "he_map")

    def test_invalid_occupancy_and_quaternion_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            HEVisualSlamBridge.occupancy_from_ros(ros_map([0], 2, 2))
        message = ros_odom()
        message.pose.pose.orientation = pose(quaternion=(0, 0, 0, 0)).orientation
        with self.assertRaises(ValueError):
            HEVisualSlamBridge.odometry_from_ros(message)

    def test_path_conversion_preserves_pose_order_and_frame(self) -> None:
        message = types.SimpleNamespace(
            header=header(100.0),
            poses=[
                types.SimpleNamespace(header=header(99.0), pose=pose(1.0)),
                types.SimpleNamespace(header=header(100.0), pose=pose(2.0)),
            ],
        )
        result = HEVisualSlamBridge.path_from_ros(message)
        self.assertEqual(result.frame_id, "he_map")
        self.assertEqual([item.x for item in result.poses], [1.0, 2.0])

    def test_odom_info_does_not_discard_measured_latency(self) -> None:
        bridge = HEVisualSlamBridge()
        bridge._tracking["odom_latency_ms"] = 75.0
        bridge._on_odom_info(types.SimpleNamespace(lost=False, inliers=80, features=200))
        self.assertEqual(bridge._tracking["odom_latency_ms"], 75.0)
        self.assertEqual(bridge._tracking["inliers"], 80)

    def test_shadow_blueprint_contains_no_motion_modules(self) -> None:
        module_names = {atom.module.__name__ for atom in he_visual_slam_shadow.blueprints}
        self.assertNotIn("MovementManager", module_names)
        self.assertNotIn("HEConnection", module_names)
        self.assertEqual(
            module_names,
            {
                "HERTABMapShadowRunner",
                "HEVisualSlamBridge",
                "HELocalizationHealth",
                "HEVisualMapAdapter",
                "RerunBridgeModule",
            },
        )


class TestHELocalizationHealth(unittest.TestCase):
    def test_missing_inputs_are_unhealthy(self) -> None:
        result = HELocalizationHealth().evaluate(now=100.0)
        self.assertFalse(result.healthy)
        self.assertIn("pose_missing", result.reasons)
        self.assertIn("map_missing", result.reasons)
        self.assertIn("status_missing", result.reasons)

    def test_current_he_map_quality_remains_unhealthy(self) -> None:
        evaluator = HELocalizationHealth()
        evaluator._odom = Odometry(ts=100.0, frame_id="he_visual_odom", child_frame_id="base_link")
        cells = np.full(10000, -1, dtype=np.int8)
        cells[:252] = 100
        cells[:43] = 0
        evaluator._map = OccupancyGrid(grid=cells.reshape(100, 100), ts=100.0)
        evaluator._status = {
            "stamp": 100.0,
            "tracking_lost": False,
            "inliers": 79,
            "tf_ok": True,
            "tf_stamp": 100.0,
        }
        evaluator._runtime_status = {"process_alive": True, "rss_mb": 470.0}
        result = evaluator.evaluate(now=100.1)
        self.assertFalse(result.healthy)
        self.assertIn("map_known_ratio_low", result.reasons)
        self.assertAlmostEqual(result.known_ratio, 0.0252)

    def test_complete_fresh_evidence_can_be_healthy(self) -> None:
        evaluator = HELocalizationHealth()
        evaluator._odom = Odometry(ts=100.0)
        grid = np.zeros((20, 20), dtype=np.int8)
        grid[:2] = -1
        evaluator._map = OccupancyGrid(grid=grid, ts=100.0)
        evaluator._status = {
            "tracking_lost": False,
            "inliers": 50,
            "tf_ok": True,
            "tf_stamp": 100.0,
        }
        evaluator._runtime_status = {"process_alive": True, "rss_mb": 470.0}
        self.assertTrue(evaluator.evaluate(now=100.1).healthy)

    def test_stale_pose_tracking_loss_and_tf_jump_fail_closed(self) -> None:
        evaluator = HELocalizationHealth()
        evaluator._odom = Odometry(ts=98.0)
        evaluator._map = OccupancyGrid(grid=np.zeros((10, 10), dtype=np.int8), ts=100.0)
        evaluator._status = {
            "tracking_lost": True,
            "inliers": 0,
            "tf_ok": True,
            "tf_stamp": 98.0,
            "tf_translation_jump_m": 1.0,
            "tf_rotation_jump_deg": 40.0,
        }
        evaluator._runtime_status = {"process_alive": False, "rss_mb": 900.0}
        reasons = evaluator.evaluate(now=100.0).reasons
        self.assertIn("pose_stale", reasons)
        self.assertIn("tracking_lost", reasons)
        self.assertIn("tf_stale", reasons)
        self.assertIn("tf_translation_jump", reasons)
        self.assertIn("tf_rotation_jump", reasons)
        self.assertIn("slam_process_down", reasons)
        self.assertIn("slam_memory_high", reasons)


class TestHEVisualMapAdapter(unittest.TestCase):
    def test_quality_reports_known_and_free_space(self) -> None:
        grid = OccupancyGrid(grid=np.array([[-1, 0], [100, 0]], dtype=np.int8))
        valid, metrics = HEVisualMapAdapter.quality(grid)
        self.assertTrue(valid)
        self.assertAlmostEqual(metrics["known_ratio"], 0.75)
        self.assertAlmostEqual(metrics["free_ratio_of_known"], 2.0 / 3.0)


if __name__ == "__main__":
    unittest.main()
