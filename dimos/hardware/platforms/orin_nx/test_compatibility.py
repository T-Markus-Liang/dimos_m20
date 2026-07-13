from dimos.hardware.platforms.orin_nx.compatibility import (
    assess_compatibility,
    parse_cuda_version,
    parse_l4t_version,
    parse_os_release,
)


def test_parse_l4t_from_tegra_or_package_version() -> None:
    tegra = "# R36 (release), REVISION: 4.3, GCID: 38968081"
    assert parse_l4t_version(tegra) == "36.4.3"
    assert parse_l4t_version("", "36.4.3-20250107174145") == "36.4.3"


def test_parse_cuda_text_and_json() -> None:
    assert parse_cuda_version("Cuda compilation tools, release 12.6, V12.6.68") == "12.6"
    assert parse_cuda_version('{"cuda": {"version": "12.6.68"}}') == "12.6.68"


def test_parse_os_release() -> None:
    assert parse_os_release('NAME="Ubuntu"\nVERSION_ID="22.04"\n')["VERSION_ID"] == "22.04"


def test_qualified_jetson_has_no_findings() -> None:
    report = {
        "system": "Linux",
        "architecture": "aarch64",
        "ubuntu_version": "22.04",
        "l4t_version": "36.4.3",
        "cuda_version": "12.6",
        "python_version": "3.10.12",
        "memory_total_mb": 7620,
    }
    assert assess_compatibility(report) == {"errors": [], "warnings": []}


def test_preflight_separates_errors_from_ml_wheel_warning() -> None:
    report = {
        "system": "Linux",
        "architecture": "x86_64",
        "ubuntu_version": "24.04",
        "l4t_version": None,
        "cuda_version": None,
        "python_version": "3.12.2",
        "memory_total_mb": 4096,
    }
    assessment = assess_compatibility(report)
    assert "target_requires_aarch64" in assessment["errors"]
    assert "l4t_not_detected" in assessment["errors"]
    assert "unqualified_ubuntu:24.04" in assessment["errors"]
    assert "jetson_ml_wheels_are_qualified_for_cp310:not_3.12.2" in assessment["warnings"]
    assert "cuda_not_detected" in assessment["warnings"]
    assert "less_than_8gb_class_memory:4096mb" in assessment["warnings"]
