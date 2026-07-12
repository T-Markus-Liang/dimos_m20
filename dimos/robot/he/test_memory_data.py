"""Tests for HE Linux memory evidence parsers."""

import unittest

from dimos.robot.he.memory_data import (
    parse_anonymous_mappings,
    parse_kb_fields,
    parse_memory_stat,
)
from dimos.robot.he.shadow_soak import parse_tegrastats, summarize_shadow_soak


class TestHEMemoryData(unittest.TestCase):
    def test_parses_proc_and_cgroup_fields(self) -> None:
        self.assertEqual(
            parse_kb_fields("Rss: 10 kB\nPss: 4 kB\nThreads: 2\n"),
            {"Rss": 10240, "Pss": 4096},
        )
        self.assertEqual(parse_memory_stat("anon 100\nfile 20\n"), {"anon": 100, "file": 20})

    def test_reports_large_anonymous_mappings(self) -> None:
        text = """1000-2000 rw-p 00000000 00:00 0
Size:               2048 kB
Rss:                1536 kB
Anonymous:          1500 kB
2000-3000 r--p 00000000 00:00 0 /tmp/file
Size:               4096 kB
Rss:                2048 kB
Anonymous:           100 kB
"""
        self.assertEqual(
            parse_anonymous_mappings(text),
            [
                {
                    "mapping": "[anonymous]",
                    "size_bytes": 2 * 1024 * 1024,
                    "rss_bytes": 1536 * 1024,
                    "anonymous_bytes": 1500 * 1024,
                }
            ],
        )

    def test_summarizes_shadow_soak(self) -> None:
        base = {
            "service_state": "active",
            "restart_count": 0,
            "memory_current_bytes": 1200,
            "memory_max_bytes": 2560,
            "tasks_current": 300,
            "available_memory_bytes": 2 * 1024**3,
            "swap_used_bytes": 500,
            "nav_cmd_vel_publishers": 0,
            "tegrastats": {
                "gpu_percent": 10.0,
                "max_temperature_c": 60.0,
                "input_power_mw": 6000.0,
            },
            "memory_events": {"high": 0, "max": 0, "oom": 0, "oom_kill": 0},
            "errors": [],
        }
        first = {**base, "elapsed_seconds": 0.0, "cpu_usage_nsec": 10}
        last = {
            **base,
            "elapsed_seconds": 10.0,
            "cpu_usage_nsec": 10_000_000_010,
        }

        summary = summarize_shadow_soak([first, last])

        self.assertTrue(summary["accepted"])
        self.assertEqual(summary["average_cpu_cores"], 1.0)
        self.assertEqual(summary["nav_cmd_vel_publishers_max"], 0)

        failed = {
            **last,
            "service_state": "inactive",
            "nav_cmd_vel_publishers": 1,
            "memory_events": {"high": 1, "max": 0, "oom": 0, "oom_kill": 0},
        }
        reasons = summarize_shadow_soak([first, failed])["reasons"]
        self.assertIn("service_not_continuously_active", reasons)
        self.assertIn("nav_cmd_vel_publisher_present", reasons)
        self.assertIn("memory_event_triggered", reasons)

    def test_parses_tegrastats(self) -> None:
        sample = (
            "RAM 1/2MB CPU [10%@729] GR3D_FREQ 7% cpu@61.5C "
            "tj@62.1C VDD_IN 6563mW/6563mW"
        )
        self.assertEqual(
            parse_tegrastats(sample),
            {
                "gpu_percent": 7.0,
                "max_temperature_c": 62.1,
                "input_power_mw": 6563.0,
            },
        )
        self.assertIsNone(parse_tegrastats("no telemetry"))


if __name__ == "__main__":
    unittest.main()
