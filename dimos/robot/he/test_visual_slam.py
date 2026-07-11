"""Tests for the HE visual SLAM shadow adapters and health gates."""

from __future__ import annotations

import math
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import types
import unittest

import numpy as np

from dimos.msgs.nav_msgs.OccupancyGrid import OccupancyGrid
from dimos.msgs.nav_msgs.Odometry import Odometry
from dimos.robot.he.blueprints import he_visual_slam_shadow
from dimos.robot.he.sensors import HESensorBridge
from dimos.robot.he.visual_slam import (
    HELocalizationHealth,
    HERTABMapShadowRunner,
    HEVisualMapAdapter,
    HEVisualSlamBridge,
    summarize_localization_health,
    system_memory_status,
)
from dimos.visualization.rerun.bridge import RerunBridgeModule

DEPLOYMENT_DIR = Path(__file__).parent / "deployment"


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


def ros_camera_info(stamp: float = 100.0):
    return types.SimpleNamespace(
        header=header(stamp, "rgb_camera_link"),
        width=640,
        height=400,
        k=[417.0, 0.0, 320.0, 0.0, 418.0, 192.0, 0.0, 0.0, 1.0],
        p=[417.0, 0.0, 320.0, 0.0, 0.0, 418.0, 192.0, 0.0, 0.0, 0.0, 1.0, 0.0],
    )


def runtime_status(
    stamp: float = 100.0,
    *,
    process_alive: bool = True,
    rss_mb: float = 470.0,
    system_available_mb: float = 2048.0,
    swap_growth_mb: float = 0.0,
) -> dict[str, float | bool]:
    return {
        "stamp": stamp,
        "process_alive": process_alive,
        "rss_mb": rss_mb,
        "system_available_mb": system_available_mb,
        "swap_used_mb": 500.0,
        "swap_growth_mb": swap_growth_mb,
    }


class TestHEVisualSlamBridge(unittest.TestCase):
    def test_camera_info_validation_accepts_canonical_and_rejects_bad_intrinsics(self) -> None:
        status = HEVisualSlamBridge.camera_info_status(ros_camera_info(), "rgb_camera_link")
        self.assertTrue(status["camera_info_valid"])
        self.assertEqual(status["camera_info_fx"], 417.0)

        invalid = ros_camera_info()
        invalid.k[0] = 0.0
        with self.assertRaises(ValueError):
            HEVisualSlamBridge.camera_info_status(invalid, "rgb_camera_link")

        shifted = ros_camera_info()
        shifted.k[0] *= 1.1
        expected = {
            "width": 640,
            "height": 400,
            "fx": 417.0,
            "fy": 418.0,
            "cx": 320.0,
            "cy": 192.0,
        }
        with self.assertRaisesRegex(ValueError, "approved baseline"):
            HEVisualSlamBridge.camera_info_status(shifted, "rgb_camera_link", expected)

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
        ordered_module_names = [
            atom.module.__name__ for atom in he_visual_slam_shadow.blueprints
        ]
        module_names = set(ordered_module_names)
        self.assertNotIn("MovementManager", module_names)
        self.assertNotIn("HEConnection", module_names)
        self.assertEqual(
            module_names,
            {
                "HERTABMapShadowRunner",
                "HEVisualSlamBridge",
                "HELocalizationHealth",
                "HEVisualMapAdapter",
                "HESensorBridge",
                "RerunBridgeModule",
            },
        )
        self.assertEqual(ordered_module_names[0], "HESensorBridge")
        self.assertEqual(ordered_module_names[-1], "HERTABMapShadowRunner")

        atoms = {atom.module: atom for atom in he_visual_slam_shadow.blueprints}
        self.assertEqual(atoms[HESensorBridge].kwargs, {})
        self.assertEqual(atoms[RerunBridgeModule].kwargs["memory_limit"], "256MB")
        self.assertEqual(
            atoms[RerunBridgeModule].kwargs["latest_only_entities"],
            [
                "world/color_image",
                "world/depth_image",
                "world/ir_image",
                "world/pointcloud",
                "world/camera_info",
                "world/depth_camera_info",
                "world/odom",
                "world/imu",
                "world/visual_odom",
                "world/visual_map",
                "world/visual_path",
                "world/visual_status",
                "world/localization_health",
                "world/global_costmap",
            ],
        )


class TestHELocalizationHealth(unittest.TestCase):
    def test_health_summary_preserves_fault_and_recovery_transitions(self) -> None:
        samples = [
            {
                "received_at": 1.0,
                "checked_at": 1.0,
                "healthy": False,
                "reasons": ("map_known_ratio_low",),
                "pose_age_s": 0.1,
                "tf_age_s": 0.1,
                "runtime_status_age_s": 0.1,
            },
            {
                "received_at": 2.0,
                "checked_at": 2.0,
                "healthy": False,
                "reasons": ("pose_stale", "tf_stale", "map_known_ratio_low"),
                "pose_age_s": 1.1,
                "tf_age_s": 1.1,
                "runtime_status_age_s": 1.1,
            },
            {
                "received_at": 3.0,
                "checked_at": 3.0,
                "healthy": False,
                "reasons": ("map_known_ratio_low",),
                "pose_age_s": 0.1,
                "tf_age_s": 0.1,
                "runtime_status_age_s": 0.1,
            },
        ]

        summary = summarize_localization_health(samples)

        self.assertEqual(summary["samples"], 3)
        self.assertEqual(summary["healthy_samples"], 0)
        self.assertEqual(summary["reason_counts"]["pose_stale"], 1)
        self.assertEqual(summary["max_pose_age_s"], 1.1)
        self.assertEqual(summary["max_runtime_status_age_s"], 1.1)
        self.assertEqual(len(summary["transitions"]), 3)
        self.assertEqual(summary["transitions"][1]["reasons"][0], "pose_stale")

    def test_missing_inputs_are_unhealthy(self) -> None:
        result = HELocalizationHealth().evaluate(now=100.0)
        self.assertFalse(result.healthy)
        self.assertIn("pose_missing", result.reasons)
        self.assertIn("map_missing", result.reasons)
        self.assertIn("status_missing", result.reasons)

    def test_camera_info_missing_invalid_and_stale_fail_closed(self) -> None:
        evaluator = HELocalizationHealth()
        evaluator._status = {"camera_info_seen": False}
        self.assertIn("camera_info_missing", evaluator.evaluate(now=100.0).reasons)
        evaluator._status = {
            "camera_info_seen": True,
            "camera_info_valid": False,
            "camera_info_stamp": 100.0,
        }
        self.assertIn("camera_info_invalid", evaluator.evaluate(now=100.0).reasons)
        evaluator._status = {
            "camera_info_seen": True,
            "camera_info_valid": True,
            "camera_info_stamp": 98.0,
        }
        self.assertIn("camera_info_stale", evaluator.evaluate(now=100.0).reasons)

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
        evaluator._runtime_status = runtime_status()
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
        evaluator._runtime_status = runtime_status()
        self.assertTrue(evaluator.evaluate(now=100.1).healthy)

    def test_latched_map_age_is_diagnostic_unless_explicitly_gated(self) -> None:
        evaluator = HELocalizationHealth()
        evaluator._odom = Odometry(ts=100.0)
        evaluator._map = OccupancyGrid(grid=np.zeros((10, 10), dtype=np.int8), ts=1.0)
        evaluator._status = {
            "tracking_lost": False,
            "inliers": 50,
            "tf_ok": True,
            "tf_stamp": 100.0,
        }
        evaluator._runtime_status = runtime_status()
        self.assertTrue(evaluator.evaluate(now=100.1).healthy)

        gated = HELocalizationHealth(max_map_age_s=3.0)
        gated._odom = evaluator._odom
        gated._map = evaluator._map
        gated._status = evaluator._status
        gated._runtime_status = evaluator._runtime_status
        self.assertIn("map_stale", gated.evaluate(now=100.1).reasons)

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
        evaluator._runtime_status = runtime_status(process_alive=False, rss_mb=900.0)
        reasons = evaluator.evaluate(now=100.0).reasons
        self.assertIn("pose_stale", reasons)
        self.assertIn("tracking_lost", reasons)
        self.assertIn("tf_stale", reasons)
        self.assertIn("tf_translation_jump", reasons)
        self.assertIn("tf_rotation_jump", reasons)
        self.assertIn("slam_process_down", reasons)
        self.assertIn("slam_memory_high", reasons)

    def test_runtime_status_and_resource_faults_fail_closed(self) -> None:
        evaluator = HELocalizationHealth()
        evaluator._runtime_status = runtime_status(
            stamp=90.0,
            rss_mb=math.nan,
            system_available_mb=900.0,
            swap_growth_mb=65.0,
        )

        reasons = evaluator.evaluate(now=100.0).reasons

        self.assertIn("runtime_status_stale", reasons)
        self.assertIn("slam_memory_invalid", reasons)
        self.assertIn("system_memory_low", reasons)
        self.assertIn("swap_growth_high", reasons)

        evaluator._runtime_status = runtime_status()
        recovered = evaluator.evaluate(now=100.1)
        self.assertNotIn("runtime_status_stale", recovered.reasons)
        self.assertNotIn("slam_memory_invalid", recovered.reasons)
        self.assertNotIn("system_memory_low", recovered.reasons)
        self.assertNotIn("swap_growth_high", recovered.reasons)

    def test_missing_resource_fields_are_invalid(self) -> None:
        evaluator = HELocalizationHealth()
        evaluator._runtime_status = {"stamp": 100.0, "process_alive": True}

        reasons = evaluator.evaluate(now=100.1).reasons

        self.assertIn("slam_memory_invalid", reasons)
        self.assertIn("system_memory_invalid", reasons)
        self.assertIn("swap_usage_invalid", reasons)
        self.assertIn("swap_growth_invalid", reasons)

    def test_proc_memory_parser_reports_available_and_swap_used(self) -> None:
        result = system_memory_status(
            "MemAvailable: 2097152 kB\n"
            "SwapTotal: 1048576 kB\n"
            "SwapFree: 786432 kB\n"
            "SwapCached: 65536 kB\n"
        )

        self.assertEqual(result["system_available_mb"], 2048.0)
        self.assertEqual(result["swap_used_mb"], 192.0)
        with self.assertRaises(ValueError):
            system_memory_status("MemAvailable: 1 kB\n")


class TestHEVisualMapAdapter(unittest.TestCase):
    def test_quality_reports_known_and_free_space(self) -> None:
        grid = OccupancyGrid(grid=np.array([[-1, 0], [100, 0]], dtype=np.int8))
        valid, metrics = HEVisualMapAdapter.quality(grid)
        self.assertTrue(valid)
        self.assertAlmostEqual(metrics["known_ratio"], 0.75)
        self.assertAlmostEqual(metrics["free_ratio_of_known"], 2.0 / 3.0)


class TestHERTABMapRuntimeBounds(unittest.TestCase):
    def mode_check(self, env: dict[str, str] | None = None):
        clean_env = os.environ.copy()
        clean_env.pop("HE_RTABMAP_MODE", None)
        clean_env.pop("HE_RTABMAP_DB", None)
        clean_env.pop("HE_RTABMAP_RGB_TOPIC", None)
        clean_env.pop("HE_RTABMAP_DEPTH_TOPIC", None)
        clean_env.pop("HE_RTABMAP_CAMERA_INFO_TOPIC", None)
        if env:
            clean_env.update(env)
        return subprocess.run(
            [DEPLOYMENT_DIR / "run-he-rtabmap-shadow.sh", "--check-mode"],
            capture_output=True,
            check=False,
            env=clean_env,
            text=True,
            timeout=3,
        )

    def test_shadow_modes_fail_closed_on_database_reuse(self) -> None:
        default = self.mode_check()
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertIn("mode: mapping", default.stdout)
        self.assertIn("IncrementalMemory:='true'", default.stdout)

        self.assertEqual(self.mode_check({"HE_RTABMAP_MODE": "invalid"}).returncode, 2)
        self.assertEqual(self.mode_check({"HE_RTABMAP_MODE": "localization"}).returncode, 2)

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "map.db"
            new_mapping = self.mode_check({"HE_RTABMAP_DB": str(database)})
            self.assertEqual(new_mapping.returncode, 0, new_mapping.stderr)

            database.touch()
            mapping = self.mode_check({"HE_RTABMAP_DB": str(database)})
            self.assertEqual(mapping.returncode, 2)

            empty_localization = self.mode_check(
                {"HE_RTABMAP_MODE": "localization", "HE_RTABMAP_DB": str(database)}
            )
            self.assertEqual(empty_localization.returncode, 2)

            database.write_bytes(b"not sqlite")
            malformed_localization = self.mode_check(
                {"HE_RTABMAP_MODE": "localization", "HE_RTABMAP_DB": str(database)}
            )
            self.assertEqual(malformed_localization.returncode, 2)

            database.unlink()
            with sqlite3.connect(database) as sqlite_database:
                sqlite_database.execute('CREATE TABLE "Node" (id INTEGER)')
            missing_schema = self.mode_check(
                {"HE_RTABMAP_MODE": "localization", "HE_RTABMAP_DB": str(database)}
            )
            self.assertEqual(missing_schema.returncode, 2)

            with sqlite3.connect(database) as sqlite_database:
                for table in ("Admin", "Data", "Info"):
                    sqlite_database.execute(f'CREATE TABLE "{table}" (id INTEGER)')
            localization = self.mode_check(
                {"HE_RTABMAP_MODE": "localization", "HE_RTABMAP_DB": str(database)}
            )
            self.assertEqual(localization.returncode, 0, localization.stderr)
            self.assertIn("IncrementalMemory:='false'", localization.stdout)
            self.assertIn("InitWMWithAllNodes:='true'", localization.stdout)
            self.assertIn("LocalizationReadOnly:='true'", localization.stdout)
            self.assertIn("LocalizationDataSaved:='false'", localization.stdout)

    def test_shadow_input_topic_overrides_are_explicit_and_validated(self) -> None:
        default = self.mode_check()
        self.assertIn("RGB input: /aurora/rgb/image_raw", default.stdout)
        self.assertIn("depth input: /aurora/depth/image_raw", default.stdout)

        fault = self.mode_check(
            {
                "HE_RTABMAP_RGB_TOPIC": "/he/fault/rgb/image_raw",
                "HE_RTABMAP_DEPTH_TOPIC": "/he/fault/depth/image_raw",
                "HE_RTABMAP_CAMERA_INFO_TOPIC": "/he/fault/rgb/camera_info",
            }
        )
        self.assertEqual(fault.returncode, 0, fault.stderr)
        self.assertIn("RGB input: /he/fault/rgb/image_raw", fault.stdout)
        self.assertIn("depth input: /he/fault/depth/image_raw", fault.stdout)

        for topic in ("relative/topic", "/he/fault/rgb;true", "/he//fault"):
            with self.subTest(topic=topic):
                result = self.mode_check({"HE_RTABMAP_RGB_TOPIC": topic})
                self.assertEqual(result.returncode, 2)
                self.assertIn("Invalid absolute ROS topic", result.stderr)

    def watchdog(self, *args: str, env: dict[str, str] | None = None):
        clean_env = os.environ.copy()
        clean_env.pop("HE_RTABMAP_MAX_DB_MIB", None)
        clean_env.pop("HE_RTABMAP_DB_POLL_SECONDS", None)
        if env:
            clean_env.update(env)
        return subprocess.run(
            [DEPLOYMENT_DIR / "he-rtabmap-db-watchdog.sh", *args],
            capture_output=True,
            check=False,
            env=clean_env,
            text=True,
            timeout=3,
        )

    def test_shadow_uses_motion_commit_thresholds(self) -> None:
        config = (DEPLOYMENT_DIR / "he-rtabmap-shadow.yaml").read_text()
        self.assertIn('"RGBD/LinearUpdate": "0.1"', config)
        self.assertIn('"RGBD/AngularUpdate": "0.1"', config)
        self.assertIn('"Mem/NotLinkedNodesKept": "false"', config)

    def test_watchdog_default_and_configuration_boundaries(self) -> None:
        result = self.watchdog("--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("256 MiB", result.stdout)

        invalid_environments = (
            {"HE_RTABMAP_MAX_DB_MIB": "0"},
            {"HE_RTABMAP_MAX_DB_MIB": "4097"},
            {"HE_RTABMAP_MAX_DB_MIB": "invalid"},
            {"HE_RTABMAP_DB_POLL_SECONDS": "0"},
            {"HE_RTABMAP_DB_POLL_SECONDS": "61"},
        )
        for environment in invalid_environments:
            with self.subTest(environment=environment):
                self.assertEqual(self.watchdog("--check", env=environment).returncode, 2)

    def test_watchdog_reports_a_database_at_the_limit(self) -> None:
        with tempfile.NamedTemporaryFile() as database:
            database.truncate(1024 * 1024)
            result = self.watchdog(
                database.name,
                env={
                    "HE_RTABMAP_MAX_DB_MIB": "1",
                    "HE_RTABMAP_DB_POLL_SECONDS": "1",
                },
            )
        self.assertEqual(result.returncode, 42, result.stderr)
        self.assertIn("reached", result.stderr)

    def test_shadow_runner_reaps_its_process_group_within_cli_grace(self) -> None:
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import signal, time; "
                "signal.signal(signal.SIGINT, lambda *_: exit(0)); "
                "signal.signal(signal.SIGTERM, lambda *_: exit(0)); "
                "time.sleep(60)",
            ],
            start_new_session=True,
        )
        runner = HERTABMapShadowRunner()
        runner._process = process
        started = time.monotonic()
        try:
            runner._stop_process_group()
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=1.0)

        self.assertLess(time.monotonic() - started, 4.5)
        self.assertIsNotNone(process.returncode)
        self.assertIsNone(runner._process)


if __name__ == "__main__":
    unittest.main()
