"""Small, ROS-independent helpers for HE visual sensor qualification."""

from __future__ import annotations

from collections import deque
from itertools import pairwise
import json
from pathlib import Path
import statistics
import time
from typing import Any

import cv2
import numpy as np

VISUAL_FAULT_MODES = {
    "blank-rgb",
    "blank-depth",
    "blank-both",
    "drop-camera-info",
    "corrupt-camera-info",
}


def visual_fault_payload(payload: Any, stream: str, mode: str) -> bytes:
    """Return a copied image payload, blanking only the selected fault stream."""
    if mode not in VISUAL_FAULT_MODES:
        raise ValueError(f"unsupported visual fault mode: {mode}")
    if stream not in {"rgb", "depth"}:
        raise ValueError(f"unsupported visual stream: {stream}")
    blank = mode == "blank-both" or mode == f"blank-{stream}"
    return bytes(len(payload)) if blank else bytes(payload)


def should_drop_camera_info(stream: str, mode: str) -> bool:
    """Return whether the isolated RGB CameraInfo should be withheld."""
    if mode not in VISUAL_FAULT_MODES:
        raise ValueError(f"unsupported visual fault mode: {mode}")
    if stream not in {"rgb", "depth"}:
        raise ValueError(f"unsupported visual stream: {stream}")
    return mode == "drop-camera-info" and stream == "rgb"


def corrupted_camera_intrinsics(k: Any, p: Any) -> tuple[list[float], list[float]]:
    """Return malformed-but-present camera matrices with zero focal lengths."""
    corrupted_k = [float(value) for value in k]
    corrupted_p = [float(value) for value in p]
    if len(corrupted_k) != 9 or len(corrupted_p) != 12:
        raise ValueError("CameraInfo K/P matrices must have 9/12 elements")
    corrupted_k[0] = corrupted_k[4] = 0.0
    corrupted_p[0] = corrupted_p[5] = 0.0
    return corrupted_k, corrupted_p


def stamp_seconds(message: Any) -> float:
    stamp = message.header.stamp
    return float(stamp.sec) + float(stamp.nanosec) / 1_000_000_000.0


def topic_rate(stamps: list[float]) -> float:
    intervals = [b - a for a, b in pairwise(stamps) if b > a]
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


def mono8_array(message: Any) -> np.ndarray:
    if message.encoding.lower() not in {"mono8", "8uc1"}:
        raise ValueError(f"unsupported mono8 encoding: {message.encoding}")
    row_bytes = int(message.width)
    if message.step < row_bytes:
        raise ValueError("mono8 row step is shorter than the pixel payload")
    raw = np.frombuffer(message.data, dtype=np.uint8)
    required = int(message.height) * int(message.step)
    if raw.size < required:
        raise ValueError("mono8 payload is truncated")
    return np.ascontiguousarray(
        raw[:required].reshape(message.height, message.step)[:, :row_bytes]
    )


def bgr8_array(message: Any) -> np.ndarray:
    if message.encoding.lower() != "bgr8":
        raise ValueError(f"unsupported BGR encoding: {message.encoding}")
    row_bytes = int(message.width) * 3
    if message.step < row_bytes:
        raise ValueError("BGR row step is shorter than the pixel payload")
    raw = np.frombuffer(message.data, dtype=np.uint8)
    required = int(message.height) * int(message.step)
    if raw.size < required:
        raise ValueError("BGR payload is truncated")
    return np.ascontiguousarray(
        raw[:required].reshape(message.height, message.step)[:, :row_bytes]
    ).reshape(message.height, message.width, 3)


def write_visual_snapshot(
    directory: Path,
    *,
    depth_stamp: float,
    depth: np.ndarray,
    rgb_stamp: float,
    rgb: np.ndarray,
    ir_stamp: float,
    ir: np.ndarray,
    min_depth_mm: int = 150,
    max_depth_mm: int = 4000,
) -> dict[str, Any]:
    if depth.ndim != 2 or ir.shape != depth.shape or rgb.shape != (*depth.shape, 3):
        raise ValueError("RGB, IR and depth snapshot arrays must have matching image dimensions")
    directory.mkdir(parents=True, exist_ok=True)
    valid = (depth >= min_depth_mm) & (depth <= max_depth_mm)
    scale = 255.0 / max_depth_mm if max_depth_mm > 0 else 0.0
    depth_visual = np.clip(depth.astype(np.float32) * scale, 0, 255).astype(np.uint8)
    depth_visual = cv2.applyColorMap(depth_visual, cv2.COLORMAP_TURBO)
    depth_visual[~valid] = 0
    files = {
        "rgb": "rgb.png",
        "ir": "ir.png",
        "depth_mm": "depth-mm.png",
        "depth_visual": "depth-visual.png",
        "valid_mask": "valid-mask.png",
    }
    images = {
        "rgb": rgb,
        "ir": ir,
        "depth_mm": depth,
        "depth_visual": depth_visual,
        "valid_mask": valid.astype(np.uint8) * 255,
    }
    for name, image in images.items():
        if not cv2.imwrite(str(directory / files[name]), image):
            raise RuntimeError(f"failed to write snapshot image: {files[name]}")
    metadata = {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "depth_stamp": depth_stamp,
        "rgb_absolute_offset_ms": abs(rgb_stamp - depth_stamp) * 1000.0,
        "ir_absolute_offset_ms": abs(ir_stamp - depth_stamp) * 1000.0,
        "min_depth_mm": min_depth_mm,
        "max_depth_mm": max_depth_mm,
        "valid_ratio": float(np.mean(valid)),
        "files": files,
    }
    (directory / "snapshot.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return metadata


def _mask_bbox(mask: np.ndarray) -> dict[str, int | float] | None:
    rows, columns = np.nonzero(mask)
    if not rows.size:
        return None
    y_min, y_max = int(rows.min()), int(rows.max())
    x_min, x_max = int(columns.min()), int(columns.max())
    area = (y_max - y_min + 1) * (x_max - x_min + 1)
    return {
        "x_min": x_min,
        "y_min": y_min,
        "x_max": x_max,
        "y_max": y_max,
        "width": x_max - x_min + 1,
        "height": y_max - y_min + 1,
        "area_ratio": area / mask.size,
        "fill_ratio": float(np.mean(mask[y_min : y_max + 1, x_min : x_max + 1])),
    }


def _largest_component(mask: np.ndarray) -> dict[str, Any] | None:
    pending = mask.copy()
    largest: list[tuple[int, int]] = []
    height, width = mask.shape
    for start_y, start_x in zip(*np.nonzero(pending), strict=True):
        if not pending[start_y, start_x]:
            continue
        component: list[tuple[int, int]] = []
        queue = deque([(int(start_y), int(start_x))])
        pending[start_y, start_x] = False
        while queue:
            y, x = queue.popleft()
            component.append((y, x))
            for next_y, next_x in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if 0 <= next_y < height and 0 <= next_x < width and pending[next_y, next_x]:
                    pending[next_y, next_x] = False
                    queue.append((next_y, next_x))
        if len(component) > len(largest):
            largest = component
    if not largest:
        return None
    component_mask = np.zeros_like(mask)
    rows, columns = zip(*largest, strict=True)
    component_mask[rows, columns] = True
    return {
        "pixels": len(largest),
        "image_ratio": len(largest) / mask.size,
        "valid_mask_ratio": len(largest) / int(np.count_nonzero(mask)),
        "bbox": _mask_bbox(component_mask),
    }


def depth_quality(
    depth_mm: np.ndarray,
    *,
    min_depth_mm: int = 150,
    max_depth_mm: int = 4000,
) -> dict[str, Any]:
    if depth_mm.ndim != 2 or depth_mm.size == 0:
        raise ValueError("depth image must be a non-empty 2D array")
    if min_depth_mm < 0 or max_depth_mm < min_depth_mm:
        raise ValueError("depth limits must define a non-negative increasing range")
    zero = depth_mm == 0
    below_minimum = (depth_mm > 0) & (depth_mm < min_depth_mm)
    above_maximum = depth_mm > max_depth_mm
    valid = (depth_mm >= min_depth_mm) & (depth_mm <= max_depth_mm)
    height, width = depth_mm.shape
    y0 = min(int(height * 0.3), height - 1)
    y1 = max(y0 + 1, int(height * 0.7))
    x0 = min(int(width * 0.3), width - 1)
    x1 = max(x0 + 1, int(width * 0.7))
    grid = []
    for row in range(3):
        grid_row = []
        for column in range(3):
            tile = valid[
                row * height // 3 : (row + 1) * height // 3,
                column * width // 3 : (column + 1) * width // 3,
            ]
            grid_row.append(float(np.mean(tile)) if tile.size else 0.0)
        grid.append(grid_row)
    values = depth_mm[valid].astype(np.float64)
    percentiles = (
        {str(p): float(np.percentile(values, p)) for p in (5, 50, 95)} if values.size else {}
    )
    return {
        "width": width,
        "height": height,
        "valid_ratio": float(np.mean(valid)),
        "zero_ratio": float(np.mean(zero)),
        "below_minimum_nonzero_ratio": float(np.mean(below_minimum)),
        "above_maximum_ratio": float(np.mean(above_maximum)),
        "uint16_max_ratio": float(np.mean(depth_mm == np.iinfo(np.uint16).max)),
        "center_40_percent_valid_ratio": float(np.mean(valid[y0:y1, x0:x1])),
        "grid_3x3_valid_ratio": grid,
        "valid_ratio_by_row": np.mean(valid, axis=1).astype(float).tolist(),
        "valid_ratio_by_column": np.mean(valid, axis=0).astype(float).tolist(),
        "valid_bbox": _mask_bbox(valid),
        "valid_depth_mm_percentiles": percentiles,
    }


def depth_temporal_quality(
    depth_frames_mm: list[np.ndarray],
    *,
    min_depth_mm: int = 150,
    max_depth_mm: int = 4000,
    stable_ratio: float = 0.9,
) -> dict[str, Any]:
    if not depth_frames_mm:
        raise ValueError("at least one depth frame is required")
    if not 0.0 < stable_ratio <= 1.0:
        raise ValueError("stable_ratio must be in (0, 1]")
    shape = depth_frames_mm[0].shape
    if len(shape) != 2 or not all(frame.shape == shape for frame in depth_frames_mm):
        raise ValueError("depth frames must be non-empty 2D arrays with equal shapes")

    counts = np.zeros(shape, dtype=np.uint32)
    for frame in depth_frames_mm:
        counts += ((frame >= min_depth_mm) & (frame <= max_depth_mm)).astype(np.uint32)
    frequency = counts.astype(np.float64) / len(depth_frames_mm)
    stable = frequency >= stable_ratio
    intermittent = (counts > 0) & (counts < len(depth_frames_mm))
    return {
        "frames": len(depth_frames_mm),
        "stable_threshold": stable_ratio,
        "mean_pixel_valid_ratio": float(np.mean(frequency)),
        "never_valid_ratio": float(np.mean(counts == 0)),
        "always_valid_ratio": float(np.mean(counts == len(depth_frames_mm))),
        "intermittent_valid_ratio": float(np.mean(intermittent)),
        "stable_valid_ratio": float(np.mean(stable)),
        "mean_valid_ratio_by_row": np.mean(frequency, axis=1).astype(float).tolist(),
        "mean_valid_ratio_by_column": np.mean(frequency, axis=0).astype(float).tolist(),
        "stable_valid_bbox": _mask_bbox(stable),
        "largest_stable_component": _largest_component(stable),
    }


def depth_ir_quality(
    depth_mm: np.ndarray,
    ir: np.ndarray,
    *,
    min_depth_mm: int = 150,
    max_depth_mm: int = 4000,
) -> dict[str, float | int | None]:
    if depth_mm.shape != ir.shape or depth_mm.ndim != 2 or depth_mm.size == 0:
        raise ValueError("depth and IR images must be non-empty and have equal 2D shapes")
    valid = (depth_mm >= min_depth_mm) & (depth_mm <= max_depth_mm)
    valid_ir = ir[valid].astype(np.float64)
    invalid_ir = ir[~valid].astype(np.float64)

    def correlation(first: np.ndarray, second: np.ndarray) -> float | None:
        if first.size < 2 or np.std(first) == 0.0 or np.std(second) == 0.0:
            return None
        return float(np.corrcoef(first, second)[0, 1])

    return {
        "pixels": int(depth_mm.size),
        "valid_depth_pixels": int(np.count_nonzero(valid)),
        "ir_mean_at_valid_depth": float(np.mean(valid_ir)) if valid_ir.size else None,
        "ir_mean_at_invalid_depth": float(np.mean(invalid_ir)) if invalid_ir.size else None,
        "depth_validity_to_ir_pearson": correlation(valid.astype(np.float64).ravel(), ir.ravel()),
        "valid_depth_to_ir_pearson": correlation(
            depth_mm[valid].astype(np.float64), valid_ir
        ),
    }


def pointcloud_xyz_quality(message: Any) -> dict[str, Any]:
    fields = {field.name: field for field in message.fields}
    if not all(name in fields for name in ("x", "y", "z")):
        raise ValueError("point cloud must contain x, y and z fields")
    if any(fields[name].datatype != 7 or fields[name].count != 1 for name in ("x", "y", "z")):
        raise ValueError("x, y and z point-cloud fields must be scalar FLOAT32")
    height, width = int(message.height), int(message.width)
    if height <= 0 or width <= 0 or message.point_step <= 0:
        raise ValueError("point cloud dimensions and point_step must be positive")
    required = int(message.row_step) * height
    if len(message.data) < required:
        raise ValueError("point-cloud payload is truncated")
    dtype = np.dtype(">f4" if message.is_bigendian else "<f4")
    coordinates = []
    for name in ("x", "y", "z"):
        field = fields[name]
        if field.offset + dtype.itemsize > message.point_step:
            raise ValueError(f"{name} field exceeds point_step")
        coordinates.append(
            np.ndarray(
                shape=(height, width),
                dtype=dtype,
                buffer=message.data,
                offset=field.offset,
                strides=(message.row_step, message.point_step),
            )
        )
    xyz = np.stack(coordinates, axis=-1).reshape(-1, 3).astype(np.float64)
    finite = np.all(np.isfinite(xyz), axis=1)
    zero = finite & np.all(xyz == 0.0, axis=1)
    usable = finite & ~zero
    ranges = np.linalg.norm(xyz[usable], axis=1)
    return {
        "points": int(xyz.shape[0]),
        "finite_xyz_ratio": float(np.mean(finite)),
        "nonfinite_xyz_ratio": float(np.mean(~finite)),
        "zero_xyz_ratio": float(np.mean(zero)),
        "usable_xyz_ratio": float(np.mean(usable)),
        "usable_range_m_percentiles": (
            {str(p): float(np.percentile(ranges, p)) for p in (5, 50, 95)}
            if ranges.size
            else {}
        ),
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


def occupancy_grid_metrics(
    data: list[int], width: int, height: int, resolution: float
) -> dict[str, float | int]:
    cells = np.asarray(data, dtype=np.int16)
    if width <= 0 or height <= 0 or cells.size != width * height:
        raise ValueError("occupancy data must match positive map dimensions")
    unknown = int(np.count_nonzero(cells < 0))
    free = int(np.count_nonzero(cells == 0))
    occupied = int(np.count_nonzero(cells >= 50))
    known = int(cells.size - unknown)
    return {
        "width": width,
        "height": height,
        "resolution_m": resolution,
        "area_m2": width * height * resolution * resolution,
        "cells": int(cells.size),
        "unknown_cells": unknown,
        "free_cells": free,
        "occupied_cells": occupied,
        "known_ratio": known / cells.size,
        "occupied_ratio_of_known": occupied / known if known else 0.0,
    }
