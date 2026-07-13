import json

import pytest

from dimos.hardware.platforms.orin_nx.storage_health import (
    main,
    parse_nvme_smart,
    summarize_storage_health,
)

HEALTHY = """critical_warning : 0
available_spare : 99%
available_spare_threshold : 32%
unsafe_shutdowns : 2
media_errors : 0
"""


def test_accepts_clean_storage() -> None:
    summary = summarize_storage_health(HEALTHY, "ordinary boot log\n")
    assert summary["healthy"] is True
    assert summary["reasons"] == []


def test_rejects_media_and_kernel_errors() -> None:
    smart = HEALTHY.replace("media_errors : 0", "media_errors : 472")
    kernel = "blk_update_request: critical medium error, dev nvme0n1\n"
    summary = summarize_storage_health(smart, kernel)
    assert summary["healthy"] is False
    assert "nvme_media_errors" in summary["reasons"]
    assert "kernel_storage_errors" in summary["reasons"]


def test_rejects_warning_and_low_spare() -> None:
    smart = HEALTHY.replace("critical_warning : 0", "critical_warning : 0x1")
    smart = smart.replace("available_spare : 99%", "available_spare : 10%")
    reasons = summarize_storage_health(smart, "")["reasons"]
    assert "nvme_critical_warning" in reasons
    assert "nvme_spare_below_threshold" in reasons


def test_requires_complete_smart_contract() -> None:
    with pytest.raises(ValueError, match="missing NVMe SMART fields"):
        parse_nvme_smart("media_errors : 0\n")


def test_cli_writes_report_and_fails_closed(tmp_path) -> None:
    smart = tmp_path / "smart.txt"
    kernel = tmp_path / "kernel.txt"
    output = tmp_path / "report.json"
    smart.write_text(HEALTHY.replace("media_errors : 0", "media_errors : 1"))
    kernel.write_text("")

    result = main(
        [
            "--device",
            "/dev/test",
            "--smart-input",
            str(smart),
            "--kernel-input",
            str(kernel),
            "--output",
            str(output),
        ]
    )

    report = json.loads(output.read_text())
    assert result == 1
    assert report["device"] == "/dev/test"
    assert report["summary"]["reasons"] == ["nvme_media_errors"]
