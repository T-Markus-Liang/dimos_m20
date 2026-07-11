# HE Visual Input Outage And Recovery

Date: 2026-07-11 23:45-23:49 CST

Status: motion-free Aurora input-loss detection and recovery passed

## Safety Scope

The test used read-only RTAB-Map localization in `he-visual-slam-shadow`.
`MovementManager` and `HEConnection` were absent, `/he/nav_cmd_vel` had zero
publishers, and no command topic was published. `he-dimos-sense` was stopped to
release the Rerun port. The Aurora service was the only injected fault.

The health observer was the bounded read-only
`benchmark-he-localization-health.py` pLCM subscriber. It publishes nothing.

## Stable Baseline

An independent eight-second baseline captured 135 health samples. Every sample
contained only `map_known_ratio_low`, the expected fail-closed result for the
2.851% known map. Maximum pose age was 0.368s and maximum TF age was 0.510s.

The baseline is intentionally not `healthy=true`; the input-loss gate is proven
by reasons added during the fault and removed after recovery.

## Fault Timeline

The 30-second observer started at epoch `1783784790.537209257`. Aurora was
stopped after five seconds and remained inactive for 7.014s:

- service inactive: `1783784795.594591701`;
- service start requested: `1783784802.608969305`;
- service active: `1783784802.639092307`.

The 444 captured samples showed these transitions relative to service state:

| Transition | Delay |
| --- | ---: |
| `pose_stale` added | 0.459s after inactive |
| `tf_stale` added | 1.032s after inactive |
| stale TF became `tf_unavailable` | 5.031s after inactive |
| `pose_stale` removed | 3.947s after active |
| original baseline fully restored | 3.994s after active |

Maximum observed pose and TF ages were 11.011s and 4.961s. Reason counts were:

- `map_known_ratio_low`: 444;
- `pose_stale`: 115;
- `tf_stale`: 44;
- `tf_unavailable`: 67.

No fresh `OdomInfo` exists while camera frames are absent, so the last inlier
and `tracking_lost` values remain cached. Fail-closed detection is provided by
pose and TF freshness, then explicit TF unavailability. This is acceptable for
input outage, but future tracking-loss tests with frames still arriving must
separately prove the `tracking_lost` and inlier gates.

## Recovery And Closeout

A separate five-second post-recovery sample captured 84 messages. All returned
to the single baseline reason `map_known_ratio_low`; maximum pose and TF ages
were 0.392s and 0.585s.

The first short sensor verifier immediately after service restart observed RGB
at only 2.68Hz, so recovery was not declared from systemd state alone. After an
additional convergence wait, the repeated quality gate measured RGB/IR around
14.29Hz, depth 13.89Hz with 28.1% valid pixels, and a valid 256000-point cloud.

The shadow stack then stopped normally with SIGTERM and left no native process
or Rerun port. `he-dimos-sense` and `aurora930` were restored active with zero
restarts. The independent read-only gate passed and navigation publishers
remained zero.

## Evidence Files

- `2026-07-11_2345_health-baseline.json`;
- `2026-07-11_2345_health-outage-recovery.json`;
- `2026-07-11_2345_health-outage-events.json`;
- `2026-07-11_2345_health-post-recovery.json`.

This closes complete Aurora input-loss detection and recovery in static shadow
mode. It does not close partial stream loss, bad-but-fresh images, moving
tracking loss, loop closure, displaced-start relocalization or navigation.
