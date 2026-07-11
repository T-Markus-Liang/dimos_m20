# HE Direct CameraInfo Health Gate

- Date: 2026-07-12 01:05-01:07 CST
- Orin code commit: `6015a9c9fc9397913362ca1f1339e909effcc174`
- Vehicle: lifted and stationary
- Runtime: read-only RTAB-Map localization on isolated inputs
- Motion output: absent; `/he/nav_cmd_vel` publishers stayed zero

## Validator

`HEVisualSlamBridge` now subscribes to the exact CameraInfo topic configured for
RTAB-Map. It checks positive dimensions, expected `rgb_camera_link`, finite K/P
matrix lengths, positive focal lengths, in-image principal point and homogeneous
matrix terms. Health exposes `camera_info_missing`, `camera_info_invalid` and
`camera_info_stale` independently of RTAB-Map odometry output.

Canonical Aurora CameraInfo was accepted at 640x400 with approximately
`fx=417.242`, `fy=418.117`, `cx=320.197`, `cy=191.827`.

## Malformed-But-Present Calibration

The proxy published 41 RGB CameraInfo messages with K/P focal lengths set to
zero while RGB/depth images and all messages remained present.

| Transition | Delay |
| --- | ---: |
| `camera_info_invalid` added | 0.363s after fault |
| `pose_stale` added | 0.491s after fault |
| `tf_stale` added | 0.963s after fault |
| `tf_unavailable` replaced `tf_stale` | 4.963s after fault |
| `camera_info_invalid` removed | 0.009s after recovery |
| original `map_known_ratio_low` baseline restored | 0.209s after recovery |

This proves malformed-but-present focal calibration is rejected directly rather
than waiting only for visual odometry to stop.

## Missing Calibration Re-Test

The updated bridge re-ran CameraInfo-only drop with 31 RGB CameraInfo messages
received but zero published during the six-second fault. RGB/depth images stayed
fresh.

| Transition | Delay |
| --- | ---: |
| `pose_stale` added | 0.345s after fault |
| `tf_stale` added | 0.745s after fault |
| `camera_info_stale` added | 0.946s after fault |
| `tf_unavailable` replaced `tf_stale` | 4.745s after fault |
| `camera_info_stale` removed | 0.103s after recovery |
| original baseline restored | 0.327s after recovery |

Startup briefly emitted `camera_info_missing` before the first calibration
message. This is expected fail-closed initialization and cleared once canonical
CameraInfo arrived.

## Persistence And Cleanup

Both tests left the read-only database SHA-256 unchanged at
`144b31d0174ab3f4b743530006664ca5fb37e9f30b7e50392d7bc40bb0cd7e7f`.
The final sensor and independent read-only gates passed; bridge memory was about
866MiB, available memory about 3.4GiB, services had zero restarts and no fault,
RTAB-Map or command publisher remained.

Raw evidence:

- `2026-07-12_0106_corrupt-camera-info-fault.json`
- `2026-07-12_0106_corrupt-camera-info-health.json`
- `2026-07-12_0107_drop-camera-info-v2-fault.json`
- `2026-07-12_0107_drop-camera-info-v2-health.json`

This closes static missing and structurally malformed CameraInfo detection. It
does not prove detection of plausible-but-wrong calibrated values, physical
camera-to-base/IMU extrinsics, or moving synchronization failures.
