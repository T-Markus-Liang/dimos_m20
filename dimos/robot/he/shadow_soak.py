"""Pure parsing and summary helpers for bounded HE shadow soaks."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
import math
from pathlib import Path
import re
import statistics
from typing import Any

_GPU = re.compile(r"\bGR3D_FREQ\s+(\d+)%")
_TEMPERATURE = re.compile(r"\b[^\s@]+@([0-9]+(?:\.[0-9]+)?)C")
_POWER = re.compile(r"\bVDD_IN\s+(\d+)mW/")
_VOLATILE_ROOTS = (Path("/tmp"), Path("/run"), Path("/dev/shm"))


def is_volatile_output(path: Path) -> bool:
    """Reject soak evidence paths that are expected to disappear on reboot."""
    resolved = path.expanduser().resolve(strict=False)
    return any(resolved.is_relative_to(root) for root in _VOLATILE_ROOTS)


def parse_tegrastats(text: str) -> dict[str, float] | None:
    """Extract compact GPU, temperature and input-power evidence from one line."""
    line = next((item for item in text.splitlines() if "GR3D_FREQ" in item), "")
    gpu = _GPU.search(line)
    temperatures = [float(value) for value in _TEMPERATURE.findall(line)]
    power = _POWER.search(line)
    if not gpu or not temperatures:
        return None
    result = {
        "gpu_percent": float(gpu.group(1)),
        "max_temperature_c": max(temperatures),
    }
    if power:
        result["input_power_mw"] = float(power.group(1))
    return result


def summarize_shadow_soak(
    samples: Sequence[dict[str, Any]],
    *,
    minimum_available_bytes: int = 1024**3,
    maximum_swap_growth_bytes: int = 64 * 1024**2,
) -> dict[str, Any]:
    """Summarize samples and return explicit fail-closed acceptance reasons."""
    if not samples:
        raise ValueError("no shadow soak samples")

    memory = [int(sample["memory_current_bytes"]) for sample in samples]
    available = [int(sample["available_memory_bytes"]) for sample in samples]
    swap = [int(sample["swap_used_bytes"]) for sample in samples]
    tasks = [int(sample["tasks_current"]) for sample in samples]
    gpu = [float(sample["tegrastats"]["gpu_percent"]) for sample in samples]
    temperatures = [
        float(sample["tegrastats"]["max_temperature_c"]) for sample in samples
    ]
    powers = [
        float(sample["tegrastats"]["input_power_mw"])
        for sample in samples
        if "input_power_mw" in sample["tegrastats"]
    ]
    nav_publishers = [int(sample["nav_cmd_vel_publishers"]) for sample in samples]
    restart_counts = [int(sample["restart_count"]) for sample in samples]
    service_states = Counter(str(sample["service_state"]) for sample in samples)
    errors = [str(error) for sample in samples for error in sample.get("errors", ())]
    event_names = ("high", "max", "oom", "oom_kill")
    event_deltas = {
        name: int(samples[-1]["memory_events"].get(name, 0))
        - int(samples[0]["memory_events"].get(name, 0))
        for name in event_names
    }

    duration = float(samples[-1]["elapsed_seconds"]) - float(
        samples[0]["elapsed_seconds"]
    )
    cpu_seconds = (
        int(samples[-1]["cpu_usage_nsec"]) - int(samples[0]["cpu_usage_nsec"])
    ) / 1e9
    memory_max = min(int(sample["memory_max_bytes"]) for sample in samples)
    swap_growth = max(swap) - swap[0]
    reasons: list[str] = []
    if len(samples) < 2:
        reasons.append("insufficient_samples")
    if service_states != {"active": len(samples)}:
        reasons.append("service_not_continuously_active")
    if max(restart_counts) != 0:
        reasons.append("service_restarted")
    if max(nav_publishers) != 0:
        reasons.append("nav_cmd_vel_publisher_present")
    if max(memory) >= memory_max:
        reasons.append("memory_max_reached")
    if min(available) < minimum_available_bytes:
        reasons.append("system_memory_low")
    if swap_growth > maximum_swap_growth_bytes:
        reasons.append("swap_growth_high")
    if any(event_deltas.values()):
        reasons.append("memory_event_triggered")
    if errors:
        reasons.append("sample_error")
    if not math.isfinite(cpu_seconds) or cpu_seconds < 0.0:
        reasons.append("cpu_usage_invalid")

    return {
        "accepted": not reasons,
        "reasons": reasons,
        "sample_count": len(samples),
        "duration_seconds": duration,
        "service_states": dict(sorted(service_states.items())),
        "restart_count_max": max(restart_counts),
        "nav_cmd_vel_publishers_max": max(nav_publishers),
        "memory_current_bytes": {
            "min": min(memory),
            "median": statistics.median(memory),
            "max": max(memory),
        },
        "memory_max_bytes": memory_max,
        "available_memory_bytes_min": min(available),
        "swap_used_bytes": {
            "initial": swap[0],
            "final": swap[-1],
            "max": max(swap),
            "max_growth": swap_growth,
        },
        "tasks_current_max": max(tasks),
        "memory_event_deltas": event_deltas,
        "average_cpu_cores": cpu_seconds / duration if duration > 0.0 else None,
        "gpu_percent_median": statistics.median(gpu),
        "gpu_percent_max": max(gpu),
        "temperature_c_max": max(temperatures),
        "input_power_mw_median": statistics.median(powers) if powers else None,
        "sample_errors": errors,
    }
