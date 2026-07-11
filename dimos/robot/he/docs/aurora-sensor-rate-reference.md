# HE Aurora Sensor Rate Reference

## Purpose

This document separates the Aurora driver's raw ROS rate from the deliberately
bounded DimOS/Rerun rate. A low visualization rate must not be interpreted as a
camera hardware limit or reused as an SLAM requirement without re-evaluation.

Measurements were taken on the HE Orin NX on 2026-07-11 while the vehicle was
static. Rates are observed values, not hard real-time guarantees.

## Raw Aurora Output

| ROS topic | Message | Format | Resolution/size | Observed rate |
| --- | --- | --- | --- | ---: |
| `/aurora/rgb/image_raw` | `sensor_msgs/Image` | `bgr8` | 640x400 | about 15Hz |
| `/aurora/depth/image_raw` | `sensor_msgs/Image` | `mono16` | 640x400 | about 15Hz |
| `/aurora/ir/image_raw` | `sensor_msgs/Image` | `mono8` | 640x400 | about 15Hz |
| `/aurora/points2` | `sensor_msgs/PointCloud2` | XYZ | 256,000 points/frame | about 13-15Hz |
| `/aurora/rgb/camera_info` | `sensor_msgs/CameraInfo` | `plumb_bob` | 640x400 | published with camera stream |
| `/aurora/ir/camera_info` | `sensor_msgs/CameraInfo` | `plumb_bob` | 640x400 | published with depth/IR stream |

The raw point cloud was previously measured near 58MB/s. Subscribing to it is
enabled locally, but forwarding every raw frame to Rerun or over Wi-Fi is not a
valid embedded default.

## Current HESensorBridge Output

`HESensorBridge` subscribes to all six Aurora ROS topics by default. It then
rate-limits the DimOS outputs used by the current headless Rerun stack:

| DimOS output | Configuration | Default | Observed output |
| --- | --- | ---: | ---: |
| `color_image` | `color_image_max_hz` | 5Hz | about 4.4Hz |
| `depth_image` | `depth_image_max_hz` | 5Hz | about 4.4Hz |
| `ir_image` | `ir_image_max_hz` | 5Hz | about 4.4Hz |
| `pointcloud` | `pointcloud_max_hz` | 1Hz | 1Hz |
| `pointcloud` | `pointcloud_stride` | 8 | one of every 8 points |
| `camera_info` | `camera_info_max_hz` | 1Hz | 1Hz |
| `depth_camera_info` | `camera_info_max_hz` | 1Hz | 1Hz |

The rate difference is intentional. It protects the Orin and remote viewer; it
does not indicate that Aurora only produces 5Hz images or a 1Hz point cloud.
Rerun retains latest-only entities in a 256MB recording window.

## Resource Evidence

- Combined DimOS LCM output was about 7.3MB/s at the bounded rates.
- A 10-second Wi-Fi sample observed only about 18.6KB transmitted, so this
  internal multicast traffic was not exported at its local data rate.
- `he-dimos-sense` stabilized around 1008-1020MiB with `NRestarts=0`.
- The service limits remain `MemoryHigh=1GiB` and `MemoryMax=1.25GiB`.
- Depth validity has ranged from about 17.6% to 20.4% in static checks.
  Increasing frame rate does not fix this coverage problem. Global validity
  alone is insufficient; the center ROI and 3x3 spatial distribution must pass.

## Algorithm Guidance

Keep the current bounded path for visualization and operational monitoring:

```text
Aurora raw ROS -> HESensorBridge -> bounded DimOS streams -> latest-only Rerun
```

For visual SLAM or another algorithm that needs full temporal resolution, do
not raise every Rerun-facing rate to 15Hz. Add or configure a separate local
processing path and keep visualization sampled:

```text
Aurora raw 13-15Hz
    |-- local synchronized RGB/depth/IR/point-cloud path -> SLAM/perception
    `-- bounded HESensorBridge/Rerun path -> remote visualization
```

Before enabling the full-rate algorithm path, verify:

1. RGB/depth/IR timestamp offsets and whether the driver provides hardware synchronization.
2. RGB-to-depth alignment and the meaning of `align_mode`/`rgbd_enable`.
3. The low depth-validity region, camera mounting obstruction and depth mode.
4. Camera-to-IMU extrinsics, IMU axis conventions and timestamp source.
5. CPU, memory, swap, temperature and dropped frames with Rerun disabled and enabled.
6. Whether the algorithm needs raw point clouds at all; RGB-D SLAM may consume
   depth images directly and avoid the 58MB/s point-cloud conversion.

The full-rate path should remain local to Orin. Remote clients should receive
poses, health, maps, paths and sampled images/point clouds rather than every raw
sensor frame.

## Recheck Commands

Raw ROS rates and graph ownership:

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
ros2 topic hz /aurora/rgb/image_raw
ros2 topic hz /aurora/depth/image_raw
ros2 topic hz /aurora/ir/image_raw
ros2 topic hz /aurora/points2
ros2 topic info /aurora/points2 -v
```

Canonical HE quality and resource checks:

```bash
cd /home/ubuntu/he/dimos_wd_m20
.venv/bin/python dimos/robot/he/deployment/verify-he-sensors.py \
  --image-samples 5 --pointcloud-samples 2 --timeout 15
bash dimos/robot/he/deployment/verify-he-readonly.sh
systemctl show he-dimos-sense.service \
  -p MemoryCurrent -p MemoryPeak -p MemoryHigh -p MemoryMax -p NRestarts
```

SLAM admission diagnostic and bounded recording:

```bash
.venv/bin/python dimos/robot/he/deployment/diagnose-he-aurora.py \
  --samples 30 --timeout 15 --output /tmp/he-aurora-diagnostic.json \
  --snapshot-dir /tmp/he-aurora-snapshot
bash dimos/robot/he/deployment/record-he-visual-dataset.sh --dry-run
```

Controlled single-parameter experiments must use the restore-guarded runner:

```bash
sudo -n true
bash dimos/robot/he/deployment/run-he-aurora-depth-ab.sh \
  threshold_size 30 /tmp/he-aurora-threshold-30.json 30
```

The runner accepts only Aurora-effective parameters, stops the canonical driver,
launches one isolated override, records an experiment sidecar, kills the full
temporary process group, restores `aurora930.service`, and runs both live sensor
and read-only gates. It is not a dynamic `ros2 param set` wrapper.

The diagnostic reports per-topic rate and RGB-nearest timestamp offset for
depth, IR, point cloud and IMU. Depth output now separates zero, non-zero below
minimum, valid, above maximum and `65535` pixels; reports center/3x3/row/column
coverage and a validity bounding box; and measures the stable validity mask and
largest stable connected region over the bounded sample window. It also reports
depth/IR correlation and finite, zero and usable XYZ point-cloud ratios. It does
not label the sensor as synchronized merely because messages arrived at similar
rates. Timestamp statistics use only overlapping streams, so a faster stream
ending before the reference window cannot inflate the reported edge offset.

The Aurora-specific source audit is recorded in
`docs/he/evidence/2026-07-11_1644_aurora-depth-driver-audit.md`. Parameters such
as `slam_mode`, `mtof_crop_*` and fusion/scatter filter thresholds are declared
by the shared driver base but are not applied by the Aurora930 device path.
Do not use their presence in `ros2 param list` as an A/B test rationale.

`--snapshot-dir` is opt-in and writes the nearest RGB/IR frame, raw 16-bit
millimetre depth, a display-only depth color map, a binary valid mask and
`snapshot.json`. It is intended for installation/occlusion inspection and is
not a recording mode; the default diagnostic writes no images.

The corrected 2026-07-11 run is stored at
`docs/he/evidence/2026-07-11_1338_aurora-diagnostic.json`. It measured IMU-to-RGB
nearest offset at 5.81ms median and 10.29ms P95. Camera streams often had equal
timestamps, but occasional one-frame gaps put RGB-depth P95 at 68.35ms. The
driver was `align_mode=true`, `depth_correction=true` and `rgbd_enable=false`.
Its own documentation states that RGB-D mode obtains all four camera outputs
from one RGB-D frame. The isolated A/B test did not improve camera pairing:
RGB-depth P95 remained about 65ms, point-cloud rate fell from 14.49Hz to
12.20Hz and point-cloud P95 grew from 51.45ms to 125.20ms. Keep
`rgbd_enable=false`; see `docs/he/evidence/2026-07-11_1346_aurora-rgbd-ab.md`.

Depth validity was 20.51% globally, 15.76% in the center 40%, and only about
4.9-5.7% in the lower-third tiles. This spatial distribution does not yet pass
the visual-navigation sensor gate.

The enhanced spatial/temporal qualification and controlled effective-parameter
A/B are recorded in `docs/he/evidence/2026-07-11_1831_aurora-depth-parameter-ab.md`.
None of threshold 30, indoor laser mode, disabled alignment or disabled depth
correction resolved the stable coverage gap. Keep the canonical values and do
not approve RGB-D navigation from global validity alone.

The bounded raw field-of-view and USB audit is in
`docs/he/evidence/2026-07-11_1843_aurora-field-of-view-usb-audit.md`. The upper
half was 48.69% valid and lower half 7.51%; RGB/IR were complete and no bracket
occluded the image. The pattern follows the smooth floor at a grazing angle.
Aurora is also on a shared 480Mbps hub, which remains a throughput qualification
risk but has no observed reset/stall evidence and does not alone explain the
stable geometric mask.

A 2026-07-12 timing A/B found that the existing single-threaded ROS executor
also contributes to receive gaps: with Sense active, depth/point-cloud estimated
missing ratios were 10.8%/34.0%; with Sense stopped and the diagnostic as the
only subscription chain they fell to 1.6%/16.1%. RGB and IR improved more
modestly. The candidate bridge therefore places point-cloud callbacks in a
separate mutually exclusive callback group under a fixed two-thread executor.
Topics, default modalities, 1Hz point-cloud output and stride 8 are unchanged.
Retain this candidate only if the equivalent Orin test improves continuity
without a material CPU, memory, swap or output-rate regression.
