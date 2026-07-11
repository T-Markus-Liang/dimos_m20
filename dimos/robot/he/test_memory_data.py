"""Tests for HE Linux memory evidence parsers."""

import unittest

from dimos.robot.he.memory_data import (
    parse_anonymous_mappings,
    parse_kb_fields,
    parse_memory_stat,
)


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


if __name__ == "__main__":
    unittest.main()
