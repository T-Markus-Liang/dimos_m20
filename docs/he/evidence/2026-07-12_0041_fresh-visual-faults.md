# HE Fresh Visual Fault Injection

- Date: 2026-07-12 00:39-00:41 CST
- Orin code commit: `0e3ef1bc076eef3f5f2e14aaaa4219ea0f6e69f5`
- Vehicle state: lifted and stationary
- Runtime: read-only RTAB-Map localization, isolated `/he/fault/*` inputs
- Motion path: absent; `/he/nav_cmd_vel` publishers remained zero

## Method

`inject-he-visual-fault.py` copied live Aurora RGB, depth and camera calibration
to isolated topics. It waited for both RTAB-Map image subscribers, then ran 12
seconds of pass-through, 8 seconds with one image payload replaced by zeros,
and 12 seconds of pass-through recovery. Header stamps continued to come from
the live Aurora messages. The saved database stayed in read-only localization
mode.

The proxy completed 42-44 publishes per image stream during each eight-second
fault, approximately 5.25-5.5Hz. Baseline and recovery were about 14-15Hz. The
lower fault-phase rate is a reliable-DDS/backpressure limitation of this proxy,
but it is still continuous fresh input rather than an input outage.

## Blank RGB

The RGB fault started at epoch `1783787939.7512033` and recovery started at
`1783787947.7949312`.

| Health transition | Delay from phase start |
| --- | ---: |
| `pose_stale` added | 0.248s after fault |
| `tracking_lost` + `inliers_low` added | 0.694s after fault |
| `tf_stale` added | 0.853s after fault |
| `tf_unavailable` replaced `tf_stale` | 4.894s after fault |
| `tracking_lost` + `inliers_low` removed | 0.251s after recovery |
| `pose_stale` removed | 0.285s after recovery |
| original `map_known_ratio_low` baseline restored | 0.451s after recovery |

This proves the live `OdomInfo.lost` and inlier gates, in addition to pose/TF
freshness. A short `slam_latency_high` transition occurred while tracking
restarted and cleared before the baseline was restored.

## Blank Depth

The depth fault started at epoch `1783788055.1939979` and recovery started at
`1783788063.232073`.

| Health transition | Delay from phase start |
| --- | ---: |
| `pose_stale` added | 0.477s after fault |
| `tf_stale` added | 1.012s after fault |
| `tf_unavailable` replaced `tf_stale` | 4.877s after fault |
| `pose_stale` removed | 0.376s after recovery |
| original `map_known_ratio_low` baseline restored | 0.440s after recovery |

RTAB-Map did not publish a new `OdomInfo.lost=true` sample for the blank-depth
period, so cached tracking/inlier state did not add those reasons. The health
chain still failed closed through pose and TF freshness. This distinction is
important: blank RGB proves explicit tracking loss, while blank depth proves
freshness fallback, not an explicit depth-validity reason.

A normal short pose gap appeared later in the depth recovery phase and cleared
in about 0.13 seconds. It is retained in the raw health record and does not
change the fault/recovery result.

## Persistence And Cleanup

The localization database SHA-256 stayed
`144b31d0174ab3f4b743530006664ca5fb37e9f30b7e50392d7bc40bb0cd7e7f`
before and after both runs. Each shadow stack stopped normally, no RTAB-Map or
fault proxy process/topic remained, and `he-dimos-sense` was restored.

The final live sensor and independent read-only gates passed. Aurora RGB,
depth and IR were about 15.3-15.5Hz, depth validity was 26.4%,
`he-dimos-sense` used about 980MiB, both services had zero restarts, and the
motion gate remained closed.

## Raw Evidence

- `2026-07-12_0039_blank-rgb-fault.json`
- `2026-07-12_0039_blank-rgb-health.json`
- `2026-07-12_0041_blank-depth-fault.json`
- `2026-07-12_0041_blank-depth-health.json`

This closes the static bad-but-fresh RGB/depth content-fault check. It does not
close moving tracking loss, partial CameraInfo loss, dynamic-object robustness,
or physical relocalization gates.
