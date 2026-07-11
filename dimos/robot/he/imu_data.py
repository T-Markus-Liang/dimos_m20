"""Pure helpers for bounded HE IMU quality diagnostics."""

from __future__ import annotations

from itertools import pairwise
import math
import statistics
from typing import Any


def _percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    return sorted(values)[int((len(values) - 1) * ratio)]


def _vector_summary(vectors: list[list[float]]) -> dict[str, Any]:
    if not vectors:
        return {"samples": 0}
    columns = list(zip(*vectors, strict=True))
    norms = [math.sqrt(sum(value * value for value in vector)) for vector in vectors]
    return {
        "samples": len(vectors),
        "mean": [statistics.fmean(column) for column in columns],
        "stddev": [statistics.pstdev(column) for column in columns],
        "norm_median": statistics.median(norms),
        "norm_p95": _percentile(norms, 0.95),
    }


def static_vector_stability(
    stamps: list[float],
    vectors: list[list[float]],
    *,
    window_seconds: float = 60.0,
    cluster_seconds: tuple[float, ...] = (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 60.0),
) -> dict[str, Any]:
    """Summarize bounded stationary vector stability without fitting a sensor model."""
    if len(stamps) != len(vectors) or len(stamps) < 2:
        raise ValueError("stamps and vectors must contain at least two paired samples")
    if window_seconds <= 0.0 or any(value <= 0.0 for value in cluster_seconds):
        raise ValueError("stability durations must be positive")
    if any(len(vector) != 3 for vector in vectors):
        raise ValueError("stability vectors must have exactly three axes")
    if any(not math.isfinite(value) for vector in vectors for value in vector):
        raise ValueError("stability vectors must be finite")

    duration = stamps[-1] - stamps[0]
    if duration <= 0.0:
        raise ValueError("stability timestamps must span a positive duration")
    if any(later <= earlier for earlier, later in pairwise(stamps)):
        raise ValueError("stability timestamps must be strictly increasing")
    sample_period = duration / (len(stamps) - 1)

    def block_means(block_size: int) -> list[list[float]]:
        count = len(vectors) // block_size
        return [
            [
                statistics.fmean(vector[axis] for vector in vectors[start : start + block_size])
                for axis in range(3)
            ]
            for start in range(0, count * block_size, block_size)
        ]

    window_samples = max(1, round(window_seconds / sample_period))
    windows = block_means(window_samples)
    window_columns = list(zip(*windows, strict=True)) if windows else []
    allan = []
    for requested_seconds in cluster_seconds:
        cluster_samples = max(1, round(requested_seconds / sample_period))
        means = block_means(cluster_samples)
        if len(means) < 3:
            continue
        squared_differences = [
            [(later[axis] - earlier[axis]) ** 2 for axis in range(3)]
            for earlier, later in pairwise(means)
        ]
        columns = list(zip(*squared_differences, strict=True))
        allan.append(
            {
                "requested_cluster_seconds": requested_seconds,
                "effective_cluster_seconds": cluster_samples * sample_period,
                "cluster_samples": cluster_samples,
                "complete_clusters": len(means),
                "value": [math.sqrt(0.5 * statistics.fmean(column)) for column in columns],
            }
        )
    return {
        "method": "non-overlapping adjacent cluster means",
        "effective_sample_period_seconds": sample_period,
        "window_seconds_requested": window_seconds,
        "window_samples": window_samples,
        "complete_windows": len(windows),
        "window_mean_span": [max(column) - min(column) for column in window_columns],
        "window_mean_stddev": [statistics.pstdev(column) for column in window_columns],
        "allan_deviation": allan,
    }


def _quaternion_angle_degrees(first: list[float], second: list[float]) -> float:
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if first_norm == 0.0 or second_norm == 0.0:
        return math.nan
    dot = abs(sum(a * b for a, b in zip(first, second, strict=True)))
    value = max(-1.0, min(1.0, dot / first_norm / second_norm))
    return math.degrees(2.0 * math.acos(value))


def _quaternion_rpy_degrees(quaternion: list[float]) -> list[float]:
    x, y, z, w = quaternion
    norm = math.sqrt(sum(value * value for value in quaternion))
    if norm == 0.0:
        return [math.nan, math.nan, math.nan]
    x, y, z, w = (value / norm for value in quaternion)
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    pitch = math.asin(max(-1.0, min(1.0, 2.0 * (w * y - z * x))))
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return [math.degrees(value) for value in (roll, pitch, yaw)]


def summarize_imu_samples(
    stamps: list[float],
    quaternions: list[list[float]],
    gyroscopes: list[list[float]],
    accelerations: list[list[float]],
    orientation_covariances: list[list[float]],
    frame_ids: set[str],
) -> dict[str, Any]:
    """Summarize one bounded IMU stream without assuming motion or calibration."""
    intervals = [later - earlier for earlier, later in pairwise(stamps)]
    positive_intervals = [interval for interval in intervals if interval > 0.0]
    quaternion_norms = [math.sqrt(sum(value * value for value in q)) for q in quaternions]
    valid_quaternions = [
        q for q, norm in zip(quaternions, quaternion_norms, strict=True) if norm > 0.0
    ]
    rpy = [_quaternion_rpy_degrees(quaternion) for quaternion in valid_quaternions]
    first_rpy = rpy[0] if rpy else []
    final_rpy = rpy[-1] if rpy else []
    angular_velocity = _vector_summary(gyroscopes)
    linear_acceleration = _vector_summary(accelerations)
    duration = stamps[-1] - stamps[0] if len(stamps) > 1 else 0.0
    if len(stamps) > 1 and duration > 0.0:
        angular_velocity["static_stability"] = static_vector_stability(stamps, gyroscopes)
        angular_velocity["stationary_mean_integral_deg"] = [
            math.degrees(value * duration) for value in angular_velocity["mean"]
        ]
        linear_acceleration["static_stability"] = static_vector_stability(
            stamps, accelerations
        )
    return {
        "samples": len(stamps),
        "frame_ids": sorted(frame_ids),
        "duration_seconds": duration,
        "rate_hz": 1.0 / statistics.fmean(positive_intervals) if positive_intervals else 0.0,
        "interval_ms": {
            "median": statistics.median(positive_intervals) * 1000.0
            if positive_intervals
            else None,
            "p95": (_percentile(positive_intervals, 0.95) or 0.0) * 1000.0
            if positive_intervals
            else None,
            "max": max(positive_intervals) * 1000.0 if positive_intervals else None,
            "nonpositive_count": len(intervals) - len(positive_intervals),
        },
        "orientation": {
            "zero_norm_count": int(sum(norm == 0.0 for norm in quaternion_norms)),
            "norm_median": statistics.median(quaternion_norms) if quaternion_norms else None,
            "norm_max_error_from_one": max(
                (abs(norm - 1.0) for norm in quaternion_norms), default=None
            ),
            "final_rotation_from_first_deg": _quaternion_angle_degrees(
                valid_quaternions[0], valid_quaternions[-1]
            )
            if valid_quaternions
            else None,
            "max_rotation_from_first_deg": max(
                (_quaternion_angle_degrees(valid_quaternions[0], q) for q in valid_quaternions),
                default=None,
            ),
            "first_rpy_deg": first_rpy,
            "final_rpy_deg": final_rpy,
            "rpy_delta_deg": [
                end - start for start, end in zip(first_rpy, final_rpy, strict=True)
            ],
        },
        "orientation_covariance": {
            "all_zero_count": int(
                sum(
                    all(value == 0.0 for value in covariance)
                    for covariance in orientation_covariances
                )
            ),
            "unknown_count": int(
                sum(
                    bool(covariance) and covariance[0] == -1.0
                    for covariance in orientation_covariances
                )
            ),
            "nonfinite_count": int(
                sum(
                    any(not math.isfinite(value) for value in covariance)
                    for covariance in orientation_covariances
                )
            ),
        },
        "angular_velocity_rad_s": angular_velocity,
        "linear_acceleration_m_s2": linear_acceleration,
    }
