"""Small, ROS-independent helpers for HE visual sensor qualification."""

from __future__ import annotations

import statistics
from typing import Any

import numpy as np


def stamp_seconds(message: Any) -> float:
    stamp = message.header.stamp
    return float(stamp.sec) + float(stamp.nanosec) / 1_000_000_000.0


def topic_rate(stamps: list[float]) -> float:
    intervals = [b - a for a, b in zip(stamps, stamps[1:]) if b > a]
    if not intervals:
        raise ValueError("at least two increasing timestamps are required")
    return 1.0 / statistics.median(intervals)


def timestamp_alignment(reference: list[float], candidate: list[float]) -> dict[str, float | int]:
    """Measure each reference timestamp against its nearest candidate."""
    if not reference or not candidate:
        raise ValueError("both timestamp series must be non-empty")
    ordered = np.asarray(sorted(candidate), dtype=np.float64)
    signed_offsets: list[float] = []
    for stamp in reference:
        if stamp < ordered[0] or stamp > ordered[-1]:
            continue
        index = int(np.searchsorted(ordered, stamp))
        choices = []
        if index < len(ordered):
            choices.append(float(ordered[index] - stamp))
        if index:
            choices.append(float(ordered[index - 1] - stamp))
        signed_offsets.append(min(choices, key=abs))
    if not signed_offsets:
        raise ValueError("timestamp series do not overlap")
    offsets_ms = np.asarray(signed_offsets, dtype=np.float64) * 1000.0
    absolute_ms = np.abs(offsets_ms)
    return {
        "pairs": len(offsets_ms),
        "reference_samples": len(reference),
        "signed_median_ms": float(np.median(offsets_ms)),
        "absolute_median_ms": float(np.median(absolute_ms)),
        "absolute_p95_ms": float(np.percentile(absolute_ms, 95)),
        "absolute_max_ms": float(np.max(absolute_ms)),
        "within_1ms_ratio": float(np.mean(absolute_ms <= 1.0)),
        "within_10ms_ratio": float(np.mean(absolute_ms <= 10.0)),
    }


def depth_array(message: Any) -> np.ndarray:
    encoding = message.encoding.lower()
    if encoding not in {"mono16", "16uc1"}:
        raise ValueError(f"unsupported depth encoding: {message.encoding}")
    row_bytes = int(message.width) * 2
    if message.step < row_bytes:
        raise ValueError("depth row step is shorter than the pixel payload")
    raw = np.frombuffer(message.data, dtype=np.uint8)
    required = int(message.height) * int(message.step)
    if raw.size < required:
        raise ValueError("depth payload is truncated")
    rows = np.ascontiguousarray(raw[:required].reshape(message.height, message.step)[:, :row_bytes])
    wire_dtype = np.dtype(">u2" if message.is_bigendian else "<u2")
    return np.frombuffer(rows.tobytes(), dtype=wire_dtype).reshape(message.height, message.width)


def depth_quality(
    depth_mm: np.ndarray,
    *,
    min_depth_mm: int = 150,
    max_depth_mm: int = 4000,
) -> dict[str, Any]:
    if depth_mm.ndim != 2 or depth_mm.size == 0:
        raise ValueError("depth image must be a non-empty 2D array")
    valid = (depth_mm >= min_depth_mm) & (depth_mm <= max_depth_mm)
    height, width = depth_mm.shape
    y0, y1 = int(height * 0.3), int(height * 0.7)
    x0, x1 = int(width * 0.3), int(width * 0.7)
    grid = []
    for row in range(3):
        grid_row = []
        for column in range(3):
            tile = valid[
                row * height // 3 : (row + 1) * height // 3,
                column * width // 3 : (column + 1) * width // 3,
            ]
            grid_row.append(float(np.mean(tile)))
        grid.append(grid_row)
    values = depth_mm[valid].astype(np.float64)
    percentiles = (
        {str(p): float(np.percentile(values, p)) for p in (5, 50, 95)} if values.size else {}
    )
    return {
        "width": width,
        "height": height,
        "valid_ratio": float(np.mean(valid)),
        "center_40_percent_valid_ratio": float(np.mean(valid[y0:y1, x0:x1])),
        "grid_3x3_valid_ratio": grid,
        "valid_depth_mm_percentiles": percentiles,
    }


def quaternion_distance_degrees(first: np.ndarray, second: np.ndarray) -> float:
    first = np.asarray(first, dtype=np.float64)
    second = np.asarray(second, dtype=np.float64)
    first /= np.linalg.norm(first)
    second /= np.linalg.norm(second)
    dot = float(np.clip(abs(np.dot(first, second)), 0.0, 1.0))
    return float(np.degrees(2.0 * np.arccos(dot)))


def stationary_trajectory_metrics(
    stamps: list[float],
    positions: list[list[float]],
    orientations: list[list[float]],
    latencies: list[float],
) -> dict[str, float | int]:
    if len(stamps) < 2 or not (len(stamps) == len(positions) == len(orientations)):
        raise ValueError("at least two equally sized pose samples are required")
    position_array = np.asarray(positions, dtype=np.float64)
    displacement = np.linalg.norm(position_array - position_array[0], axis=1)
    steps = np.linalg.norm(np.diff(position_array, axis=0), axis=1)
    rotations = [
        quaternion_distance_degrees(np.asarray(orientations[0]), np.asarray(orientation))
        for orientation in orientations
    ]
    duration = stamps[-1] - stamps[0]
    if duration <= 0.0:
        raise ValueError("pose timestamps must span a positive duration")
    result: dict[str, float | int] = {
        "samples": len(stamps),
        "duration_seconds": duration,
        "output_rate_hz": (len(stamps) - 1) / duration,
        "final_position_drift_m": float(displacement[-1]),
        "max_position_drift_m": float(np.max(displacement)),
        "accumulated_position_motion_m": float(np.sum(steps)),
        "final_rotation_drift_deg": rotations[-1],
        "max_rotation_drift_deg": max(rotations),
    }
    if latencies:
        latency_ms = np.asarray(latencies, dtype=np.float64) * 1000.0
        result.update(
            {
                "latency_median_ms": float(np.median(latency_ms)),
                "latency_p95_ms": float(np.percentile(latency_ms, 95)),
                "latency_max_ms": float(np.max(latency_ms)),
            }
        )
    return result
