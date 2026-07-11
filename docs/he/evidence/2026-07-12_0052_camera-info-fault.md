# HE CameraInfo-Only Fault Injection

- Date: 2026-07-12 00:51-00:52 CST
- Orin code commit: `7c56a2e207e706b31f7eac4dc1c9c4e975a7c4b5`
- Vehicle state: lifted and stationary
- Runtime: read-only RTAB-Map localization, isolated `/he/fault/*` inputs
- Motion path: absent; `/he/nav_cmd_vel` publishers remained zero

## Method And Input Proof

The proxy ran 12 seconds pass-through, 8 seconds CameraInfo fault and 12 seconds
recovery. RGB and depth images remained fresh and untouched. During the fault:

- RGB images published: 43;
- depth images published: 43;
- RGB CameraInfo received from Aurora: 42;
- RGB CameraInfo published to RTAB-Map: 0;
- depth CameraInfo received and published: 42.

This proves the tested fault was CameraInfo-only, not a camera service outage or
image-content fault. Reliable DDS backpressure again reduced the isolated fault
stream to roughly 5.4Hz, but messages continued throughout the eight seconds.

## Health Timeline

The fault began at epoch `1783788719.4693594` and recovery began at
`1783788727.397042`.

| Health transition | Delay from phase start |
| --- | ---: |
| `pose_stale` added | 0.316s after fault |
| `tf_stale` added | 0.719s after fault |
| `tf_unavailable` replaced `tf_stale` | 4.771s after fault |
| `pose_stale` removed | 0.219s after recovery |
| original `map_known_ratio_low` baseline restored | 0.244s after recovery |

No new `tracking_lost` or `inliers_low` reason appeared. RTAB-Map stopped
producing synchronized odometry/status when RGB CameraInfo was absent, so the
health chain failed closed through pose and TF freshness. This is synchronization
loss evidence, not explicit tracking-loss evidence.

A brief pose-stale transition occurred just before the fault and additional
short pose gaps occurred during recovery. Each cleared quickly and is retained
in the raw health JSON rather than removed from the result.

## Persistence And Cleanup

The read-only database SHA-256 remained
`144b31d0174ab3f4b743530006664ca5fb37e9f30b7e50392d7bc40bb0cd7e7f`.
No RTAB-Map/fault process or topic remained. Both services were active with zero
restarts and the independent read-only gate passed.

The first short post-restore quality sample reported RGB/depth/IR
`15.38/9.62/15.38Hz`; after five more seconds a second pass reported
`14.18/14.18/9.95Hz`. Both passed the bounded quality gate. This confirms
recovery while retaining the known short-window modality-rate variability.

## Raw Evidence

- `2026-07-12_0052_drop-camera-info-fault.json`
- `2026-07-12_0052_drop-camera-info-health.json`

This closes static CameraInfo-only synchronization-loss detection and recovery.
It does not close malformed-but-present calibration, moving synchronization
failures, dynamic scenes or navigation admission.
