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
- Aurora SDK 1.1.22 reports support depth range `0.3~1m` and
  `synced_two_images=0`. This conflicts with live valid-depth p50/p95 of
  1240/2522mm and therefore remains a vendor-clarification item, not an
  algorithm cutoff. Hardware RGB-depth synchronization remains unclaimed; see
  `evidence/2026-07-12_0213_aurora-sdk-support-probe.md`.
- A 598-second raw IMU capture found a stable but unacceptable x gyro mean of
  0.03253rad/s (about 1.864deg/s), versus a 0.000479rad/s span across nine
  60-second block means. Uncompensated mean integration was 1114.6deg. Raw IMU
  remains excluded pending physical calibration; see
  `evidence/2026-07-12_0134_imu-static-stability.md`.
- Dynamic `he_map -> he_visual_odom -> base_link` TF was observed without
  missing-TF or bad-sync warnings after tuning synchronization to 20ms.
- Raw evidence is under `docs/he/evidence/2026-07-11_1418_rtabmap-*` and
  `docs/he/evidence/2026-07-11_1430_rtabmap-static-map.json`.

## Alternatives

- Isaac ROS Visual SLAM remains the preferred accelerated platform-upgrade
  candidate, but RGB-D requires release 4.4+ on Noble/Jazzy. Humble-compatible
  release 3.2 does not provide equivalent RGB-D support.
- OpenVINS remains the lightweight VIO fallback only after camera/IMU
  calibration and timing qualification. Current raw gyro fails admission and
  cannot be connected as-is. OpenVINS does not directly solve occupancy mapping.
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
fatal. The runner now has a fail-closed mode contract: `mapping` refuses any
existing explicit database, while `localization` requires an existing non-empty
database, verifies the core RTAB-Map SQLite schema, and forces non-incremental,
read-only operation with all saved nodes initialized in working memory. This
provides a safe map-load path but does not prove displaced-start or moving
relocalization.

The first static Orin qualification now proves the mode contract end to end. A
one-node mapping database passed SQLite integrity, then produced the identical
83x60 occupancy map in read-only localization mode. RTAB-Map restored the saved
map correction, reported a good localization candidate, emitted pose/map/TF
without tracking loss, and left database size, mtime and SHA-256 unchanged.
This closes same-scene map loading only; moving and displaced-start
relocalization remain exit gates.

A static Aurora service outage also verified the fail-closed freshness path.
`pose_stale` appeared 0.459s after input became inactive, `tf_stale` at 1.032s,
and the state returned to the original poor-map baseline 3.994s after service
activation. This proves total visual-input loss detection, not bad-but-fresh
image or moving tracking-loss detection.

Isolated fresh-content faults now provide the static bad-image evidence. Blank
RGB added `pose_stale` in 0.248s, `tracking_lost/inliers_low` in 0.694s and
`tf_stale` in 0.853s; pass-through recovery restored the original baseline in
0.451s. Blank depth added `pose_stale` in 0.477s and `tf_stale` in 1.012s, then
recovered in 0.440s. RTAB-Map emitted no new explicit lost/inlier status for
blank depth, so that mode is protected by pose/TF freshness rather than an
independent depth-validity reason. Moving and dynamic-scene failures remain
unqualified.

Withholding only RGB CameraInfo while RGB/depth images stayed fresh added
`pose_stale` in 0.316s and `tf_stale` in 0.719s, then restored the baseline
0.244s after calibration resumed. No explicit tracking/inlier reason appeared;
the synchronization failure is contained by pose/TF freshness. This does not
qualify malformed-but-present calibration or moving synchronization.

The bridge now validates the exact RTAB-Map CameraInfo directly. Zero focal
lengths triggered `camera_info_invalid` in 0.363s and the reason cleared 0.009s
after valid calibration resumed. A missing calibration re-test triggered
`camera_info_stale` in 0.946s and recovered in 0.103s. Structurally valid but
out-of-baseline calibration was then tested separately: 31 RGB CameraInfo
messages with focal lengths shifted by 10% and principal points by 10px added
`camera_info_invalid` in 0.286s, cleared it 0.135s after recovery and restored
the original baseline in 0.510s. The database hash and all motion gates remained
unchanged. This qualifies runtime configuration-drift detection only; physical
target calibration and camera-to-base/camera-to-IMU extrinsics remain outside
the static gate. See `evidence/2026-07-12_0118_intrinsic-baseline-drift.md`.

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

The runtime status contract is now fail-closed as well as bounded. The runner
publishes its process-group RSS, system available memory, current swap use and
swap growth relative to runner startup once per second. Localization health
rejects status older than 2.5 seconds, missing/non-finite/negative resource
values, RSS above 768MB, available memory below 1GiB or swap growth above
64MB. These thresholds protect the shadow baseline from stale monitoring and
system pressure; they do not replace the database watchdog or systemd limits.

Static Orin fault qualification proved the contract with real runner values.
An 8GiB test threshold added `system_memory_low` to all 184 health samples;
restoring the 1GiB default removed that reason from all 187 samples while the
existing `map_known_ratio_low` remained. Process-group RSS was about 434-435MB,
available memory about 3.29-3.30GiB, swap growth zero and maximum runtime status
age about 1.08s. Both runs stopped with ordinary SIGTERM and the final sensor
and read-only gates passed. See
`evidence/2026-07-12_0325_slam-resource-health.md`.

The same test exposed a host-global Coordinator RPC constraint:
`he-dimos-sense` and the complete shadow blueprint cannot run as concurrent
DimOS coordinators. The shadow blueprint therefore includes `HESensorBridge`
directly. During shadow operation, one coordinator provides both the native
full-rate ROS SLAM path and the sampled latest-only Rerun sensor path; Sense is
stopped and later restored under an EXIT trap. The combined runtime resource
budget still requires Orin qualification before this architecture gate closes.

The first combined 10-minute Orin run kept all eight sampled streams and native
SLAM active, but failed the resource gate: four dedicated modules auto-scaled
the pool from four to eight workers, tagged-process PSS was about 1.43GiB and
runner-relative swap growth reached 84.25MiB. Health correctly reported
`swap_growth_high` for all 251 final samples. The configuration is therefore
not accepted as tested. The follow-up candidate removes the lightweight runner
manager's dedicated worker and uses the already qualified 128MB sampled-sensor
Rerun window; it requires a fresh equivalent Orin soak.

Real navigation remains prohibited until moving ATE/RPE, loop closure,
relocalization, map quality, camera extrinsics, tracking-loss detection,
resource soak and control safety gates pass after a new vehicle-down safety
confirmation.
