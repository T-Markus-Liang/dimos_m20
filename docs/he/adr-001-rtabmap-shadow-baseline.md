# ADR-001: HE RTAB-Map Shadow Baseline

Date: 2026-07-11

Status: accepted for shadow evaluation; explicitly not approved for navigation

## Context

HE has one Aurora RGB-D/IR camera and a control-board IMU on Jetson Orin NX
8GB. LD19 is retired, `/odom_raw` is command-integrated and untrusted, and the
current Jammy/Humble platform cannot use the RGB-D mode added in Isaac ROS 4.4
without a full Noble/Jazzy migration. Aurora depth is sparse and uneven: about
20.5% valid globally, 15.8% in the center 40%, and roughly 5% in lower tiles.

The evaluated alternatives and source evidence are recorded in
`visual-navigation-candidate-evaluation.md`. Public benchmark results are not
treated as HE results because inputs, hardware and alignment rules differ.

## Decision

Use the official ROS 2 Humble arm64 RTAB-Map 0.23.7 packages as the current HE
shadow baseline. Run bounded RGB-D odometry and mapping locally on Orin, adapt
their ROS outputs through `HEVisualSlamBridge`, evaluate them with
`HELocalizationHealth`, and expose a planner map only through
`HEVisualMapAdapter` after quality gates pass.

`he-visual-slam-shadow` contains no `MovementManager`, `HEConnection` or
velocity output. `HEConnection.enabled=False` and zero `/he/nav_cmd_vel`
publishers remain hard gates.

This decision is not approval for real navigation. The current static map is
82x59 at 0.05m but only 2.52% known, with 21 free and 101 occupied cells. It is
not a navigation map. The default 10% known-space gate therefore keeps
localization unhealthy and withholds `global_costmap` from planners.

## Evidence

- Static odometry: 6.31Hz, zero losses, 79/63 median/minimum inliers,
  0.48/2.58mm final/maximum position drift and 108/137ms median/P95 latency.
- Odometry peak RSS: about 214MiB and about 58% of one CPU core.
- Mapping process short-run RSS: about 255MiB.
- Dynamic `he_map -> he_visual_odom -> base_link` TF was observed without
  missing-TF or bad-sync warnings after tuning synchronization to 20ms.
- Raw evidence is under `docs/he/evidence/2026-07-11_1418_rtabmap-*` and
  `docs/he/evidence/2026-07-11_1430_rtabmap-static-map.json`.

## Alternatives

- Isaac ROS Visual SLAM remains the preferred accelerated platform-upgrade
  candidate, but RGB-D requires release 4.4+ on Noble/Jazzy. Humble-compatible
  release 3.2 does not provide equivalent RGB-D support.
- OpenVINS remains the lightweight VIO fallback after camera/IMU calibration
  and timing qualification. It does not directly solve occupancy mapping.
- ORB-SLAM3 remains an offline comparator due to GPL-3.0, old ROS integration,
  an incomplete DimOS wrapper and a known transform defect.
- DPVO is an offline learned comparator. DROID-SLAM exceeds the 8GB target's
  published memory requirement. MASt3R-SLAM and DINOv3 retain model/license and
  resource risks; DINOv3 is place-recognition or relocalization enhancement,
  not geometric SLAM.

## Consequences And Exit Gates

RTAB-Map is the only heavy SLAM runtime installed and must remain bounded. A
different baseline requires equivalent HE data, Orin resource evidence, an ADR
update and a rollback path.

Incremental mapping starts with a new bounded database by default because
visual odometry resets on each shadow start. Reusing a mapping database without
an explicit localization/resume transform caused a verified RTAB-Map graph
fatal. Database resume therefore requires an explicit `HE_RTABMAP_DB` and a
separate relocalization procedure.

A later 600-second stationary soak exposed a separate active-database growth
failure: 0.480m of accumulated frame jitter grew one database from 16.7MiB to
126.7MiB despite only 4.72mm final drift. A first 0.02m/0.01rad threshold test
made growth worse because RTAB-Map rehearses observations before the motion
gate and retained unlinked nodes by default. The corrected baseline restores
the 0.1m/0.1rad defaults and disables persistence of rehearsed/deleted nodes
that never join the graph. An independent watchdog defaults to a 256MiB hard
active-database limit and stops the complete shadow stack at the limit. Linked
map nodes and RGB-D data remain retained. File retention and this active-file
cap solve different failure modes; neither is permission to discard linked map
state during real navigation.

The corrected configuration completed a detached 600-second stationary soak.
The active database gained 1.06MiB in 590 sampled seconds versus about 110MiB
before the fix, a reduction of about 99.0%. Full-stack RSS peaked at 1.77GiB,
swap did not grow, the peak sampled temperature was 63.28C and every navigation
publisher sample remained zero. This closes the stationary active-database
growth defect for shadow evaluation; it does not close moving-map quality,
long-duration field operation or real-navigation gates.

Real navigation remains prohibited until moving ATE/RPE, loop closure,
relocalization, map quality, camera extrinsics, tracking-loss detection,
resource soak and control safety gates pass after a new vehicle-down safety
confirmation.
