# HE Runtime Intrinsic Baseline Drift Gate

- Date: 2026-07-12 01:17-01:18 CST
- Orin commit: `c14578fd93b8ea98a2a4584b080cdbe590127d6a`
- Vehicle: lifted and stationary
- Runtime: read-only localization; motion publishers zero

The approved runtime baseline is 640x400, fx/fy
417.2417/418.1166 and cx/cy 320.1967/191.8275. Runtime tolerances are 2% focal
error and 2px principal-point error. This is a configuration-drift guard, not
proof of physical calibration accuracy.

The isolated fault published 31 structurally valid CameraInfo messages with
focal lengths scaled by 1.10 and principal points shifted by 10px. RGB/depth
images remained present.

| Transition | Delay |
| --- | ---: |
| `camera_info_invalid` added | 0.286s after fault |
| `tf_stale` added | 1.030s after fault |
| `tf_unavailable` replaced `tf_stale` | 5.083s after fault |
| `camera_info_invalid` removed | 0.135s after recovery |
| original `map_known_ratio_low` baseline restored | 0.510s after recovery |

The read-only database SHA-256 remained
`144b31d0174ab3f4b743530006664ca5fb37e9f30b7e50392d7bc40bb0cd7e7f`.
Final sensor and read-only gates passed, bridge memory was about 822MiB,
available memory about 3.5GiB, services had zero restarts and no command or
fault process remained.

Raw evidence:

- `2026-07-12_0118_shift-intrinsics-fault.json`
- `2026-07-12_0118_shift-intrinsics-health.json`

This closes runtime drift beyond the approved device-reported intrinsic
tolerance. It does not validate the baseline against a calibration target or
qualify camera-to-base/camera-to-IMU physical extrinsics.
