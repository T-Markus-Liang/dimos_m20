"""Tests for the HE storage-health startup gate."""

import unittest

from dimos.robot.he.storage_health import parse_nvme_smart, summarize_storage_health

HEALTHY = """critical_warning : 0
available_spare : 99%
available_spare_threshold : 32%
unsafe_shutdowns : 2
media_errors : 0
"""


class TestHEStorageHealth(unittest.TestCase):
    def test_accepts_clean_storage(self) -> None:
        summary = summarize_storage_health(HEALTHY, "ordinary boot log\n")

        self.assertTrue(summary["healthy"])
        self.assertEqual(summary["reasons"], [])

    def test_rejects_media_and_kernel_errors(self) -> None:
        smart = HEALTHY.replace("media_errors : 0", "media_errors : 472")
        kernel = "blk_update_request: critical medium error, dev nvme0n1\n"

        summary = summarize_storage_health(smart, kernel)

        self.assertFalse(summary["healthy"])
        self.assertIn("nvme_media_errors", summary["reasons"])
        self.assertIn("kernel_storage_errors", summary["reasons"])

    def test_rejects_warning_and_low_spare(self) -> None:
        smart = HEALTHY.replace("critical_warning : 0", "critical_warning : 0x1")
        smart = smart.replace("available_spare : 99%", "available_spare : 10%")
        reasons = summarize_storage_health(smart, "")["reasons"]

        self.assertIn("nvme_critical_warning", reasons)
        self.assertIn("nvme_spare_below_threshold", reasons)

    def test_requires_complete_smart_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing NVMe SMART fields"):
            parse_nvme_smart("media_errors : 0\n")


if __name__ == "__main__":
    unittest.main()
