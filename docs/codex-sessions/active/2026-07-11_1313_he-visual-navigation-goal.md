# HE Visual Navigation Goal

## Metadata

- Date: 2026-07-11 13:13 CST
- Session id: current Codex goal thread
- Project: dimos-wd-m20
- Workspace: VM `/home/markus/work/dimos_wd_m20`; Orin `/home/ubuntu/he/dimos_wd_m20`
- Task: research, benchmark, select and integrate a visual SLAM navigation foundation for HE
- Status: active - DimOS shadow integration implemented; Orin soak pending
- Branch if relevant: `codex/he-orin` from `e495dadb`

## User Request Summary

Build a vision-only HE navigation foundation using Aurora RGB/depth/IR/point
cloud and IMU. Audit DimOS branches and current external SOTA candidates,
benchmark them against HE and Orin constraints, select one main solution, and
integrate a safe `he-visual-slam-shadow` stack with pose, map, TF and localization
health while keeping real motion disconnected.

## Work Done

- Read the complete goal objective and canonical HE deployment/sensor context.
- Confirmed VM and Orin are clean at `e495dadb` and the sensor service is active
  with zero restarts.
- Established a seven-step execution plan from baseline evidence through
  internal/external candidate audit, HE benchmark tooling, ADR, shadow
  integration and completion audit.
- Re-ran the full Orin static closeout in a clean ROS 2 Humble shell. Deployment
  integrity, 10 unit tests, isolated control dry-run, live sensors and both
  read-only gates passed. Motion remained disabled.
- Recorded current Orin evidence: `he-dimos-sense` 1006-1009MiB, zero restarts,
  about 3.5GiB available memory, 579MiB zram use, GPU about 11%, temperature
  about 59C and depth validity 20.4% in the latest check.
- Audited isolated DimOS refs for ORB-SLAM3, RTAB-Map, SLAM evaluation, PGO,
  relocalization, semantic mapping, visual-navigation sketches and learned
  depth. The existing ORB wrapper has an incomplete input contract and known
  transform defect; the existing RTAB module is an external-odometry map
  backend rather than a complete Aurora visual frontend.
- Gathered official repository, maintenance, license, platform and benchmark
  scope evidence for Isaac ROS Visual SLAM, RTAB-Map, ORB-SLAM3, OpenVINS,
  VINS-Fusion, DPVO, DROID-SLAM, MASt3R-SLAM and DINOv3.
- Drafted a unified candidate evaluation ledger plus ROS-independent depth and
  timestamp helpers, tests, an Aurora diagnostic CLI and bounded rosbag recorder.
- Committed and pushed the first qualification workflow as `6418c0fe`; Orin
  fast-forwarded to it and all 13 HE tests passed there.
- The first live diagnostic measured about 20.6% global and 15.8% center depth
  validity with especially sparse lower image tiles. Its initial IMU offset was
  invalid because the faster IMU series stopped collecting before the RGB
  window ended; fixed the tool to retain the full overlapping window and ignore
  unmatched timestamp edges before drawing a hardware conclusion.
- Corrected live evidence measured IMU-to-RGB nearest offset at 5.81ms median
  and 10.29ms P95. Camera streams have occasional one-frame gaps; RGB-depth P95
  was 68.35ms. Driver state is align/depth-correction enabled but RGB-D capture
  disabled, so an isolated RGB-D mode A/B test is required.
- Recorded a motion-disabled static rosbag at
  `/home/ubuntu/he/data/visual-navigation/20260711_133901_static-qualification`:
  3.541s, 280MiB, 669 messages, 52 samples for each Aurora stream and 171 IMU
  samples. Control topics had zero messages and safety gates passed before and
  after capture.
- Found and fixed a recorder integrity bug where `SHA256SUMS` included itself.
  Regenerated the existing list; bag, manifest and metadata all verify.
- Completed an isolated Aurora `rgbd_enable` A/B. It did not improve camera
  pairing or depth coverage and reduced point-cloud rate to 12.2Hz with worse
  timestamp gaps. Restored the unchanged systemd default (`false`) and passed
  live sensor/read-only gates.
- Verified Isaac ROS compatibility boundaries from official release trees and
  apt repositories: RGB-D starts in 4.4 on Noble/Jazzy; Jammy/Humble 3.2 lacks
  RGB-D. Confirmed official RTAB-Map 0.23.7 Humble arm64 packages are available
  on Orin without installing them yet.
- Installed only RTAB-Map 0.23.7 odometry/SLAM runtime packages on Orin. Direct
  ROS repository downloads repeatedly stalled, so official apt URIs were
  downloaded through the Tsinghua ROS mirror, checked against apt-provided MD5,
  copied to the apt cache and installed locally. Disk increase was 66,953,216
  bytes; no GUI/demo/meta package was installed.
- Live RGB-D odometry produced pose at about 8-10Hz. Bounding approximate sync
  to 20ms removed bad-pair warnings, reduced processing to about 63-76ms and
  used about 190-197MiB RSS with roughly 30-36% of one CPU core.
- Found that `ros2 run` can leave the RTAB-Map child alive after signaling the
  wrapper. Cleaned the process and switched experiments to the native binary
  under `timeout`; no persistent SLAM service exists yet.
- Added a version-controlled RTAB-Map parameter YAML and native-PID shadow
  runner. It constrains RGB/depth pairing to 20ms, mapping detection to 2Hz,
  disables TF publication and refuses to run if navigation publishers exist.
- First mapping run produced occupancy, MapData, SLAM Info and a 4.3MiB
  database, but disabling TF caused repeated missing `he_visual_odom ->
  base_link` warnings. Enable the isolated HE-prefixed map/odom TF chain for
  the next run; it does not collide with the current platform tree.
- Verified the corrected `he_map -> he_visual_odom -> base_link` chain with no
  TF or bad-sync warnings. Occupancy output was 82x59 at 0.05m and shutdown
  removed both native processes before the final read-only gate.
- Added a bounded map/TF benchmark to count known/free/occupied cells, map
  update rate, lookup failures, TF latency and static transform drift.
- Preserved the map benchmark as
  `docs/he/evidence/2026-07-11_1430_rtabmap-static-map.json`. It found only
  2.52% known cells (21 free, 101 occupied), so the map is not navigation-usable.
- Added `HEVisualSlamBridge`, `HELocalizationHealth` and `HEVisualMapAdapter`.
  The bridge converts ROS odometry, occupancy, trajectory, tracking and TF;
  health is fail-closed; and the adapter withholds low-quality maps from the
  planner-facing `global_costmap`.
- Added a process-group-owning RTAB-Map runner and registered the motion-free
  `he-visual-slam-shadow` blueprint. It contains no `MovementManager`,
  `HEConnection` or velocity output.
- Added twelve visual SLAM conversion/health/map/blueprint tests. All 29 HE unittest cases
  pass, Ruff passes, the generated blueprint registry passes in CI mode, and
  `dimos list` exposes `he-visual-slam-shadow`.
- Created ADR-001 selecting RTAB-Map only as the current shadow baseline. Real
  navigation approval is explicitly withheld.
- Pushed integration commit `e4d469cb`, fast-forwarded Orin and ran the complete
  DimOS shadow stack for about three minutes. Available memory stayed near
  3.33GiB, RTAB-Map group RSS was about 493-533MiB, and `/he/nav_cmd_vel`
  stayed at zero publishers.
- Read live health directly: current map known ratio was 2.04-2.31%, free ratio
  among known cells 12.7-15.0%, and the planner map was withheld.
- Fixed OdomInfo overwriting `odom_latency_ms` in `651af9bb`; live health then
  reported about 138ms odometry latency.
- Found a verified RTAB-Map `Memory::addLink()` fatal when a 25MiB incremental
  database was reused after visual odometry reset. `kill -0` also treated the
  dead SLAM zombie as alive and allowed odometry orphans.
- Fixed lifecycle in `3da830d3`: fresh bounded databases by default, explicit
  resume only, five-file retention, single-instance lock, `wait -n` reaping,
  no core dumps and parent-death cleanup.
- Fault-injected a SLAM child exit after the fix. Both native children were gone
  within the six-second check and health reported `slam_process_down`.
- Restored `he-dimos-sense.service` active with zero restarts after testing.
- Final `187324bd` live health had only `map_known_ratio_low`: 2.45% known,
  13.0% free among known, 145ms odometry latency and 471MiB runner RSS. System
  available memory was 3.35GiB and navigation publishers remained zero.
- Forced daemon shutdown left no native SLAM process or Rerun port, confirming
  parent-death cleanup. A transient stale point-cloud sample immediately after
  restoring the sensor service cleared; direct point-cloud/camera rates and the
  repeated live sensor quality gate passed.

## Decisions

- Preserve `HEConnection.enabled=False` and zero `/he/nav_cmd_vel` publishers
  throughout research, benchmark and shadow integration.
- Treat public leaderboard scores as supporting evidence only; HE data and Orin
  runtime evidence decide the final selection.
- Keep full-rate local algorithm inputs separate from bounded latest-only Rerun.
- Pilot RTAB-Map 0.23.7 RGB-D first because an official Humble/Jammy arm64
  package exists. Defer Isaac ROS RGB-D: it starts in release 4.4 on
  Noble/Jazzy, while HE-compatible release 3.2 lacks that mode. This is still a
  test order, not final selection; HE/Orin evidence and the ADR gate remain.
- Exclude DROID-SLAM from Orin deployment because its current official README
  requires at least 11GB GPU memory for inference.
- Require at least 10% known map cells and 10% free cells among known cells
  before exposing a visual map to planners. The current 2.52% result must stay
  unhealthy rather than being hidden by parameter relaxation.
- Treat a latched occupancy map's age as diagnostic by default. Pose and TF
  remain freshness-gated; map age can be explicitly enabled because a static
  map is allowed not to republish while the robot is stationary.

## Current State

- VM, origin and Orin are synchronized at `22473979`; both worktrees are clean.
- The final static closeout passed all 29 HE tests, blueprint discovery,
  deployment integrity, isolated control dry-run, Aurora live quality and both
  read-only gates. `he-dimos-sense` is active with zero restarts.
- DimOS visual shadow modules, lifecycle controls, ADR and evidence are
  committed, pushed and exercised on Orin. Current map quality remains
  unhealthy and no planner costmap or motion command is released.
- Aurora depth coverage, camera extrinsics, moving accuracy, loop closure and
  relocalization remain open gates. Real motion remains prohibited.

## Resume Instructions

1. Read this log, ADR-001 and the final shadow soak evidence.
2. Complete camera-to-base and camera-to-IMU extrinsic qualification.
3. Expand the public candidate ledger with directly comparable published
   benchmark tables; current source/compatibility coverage is stronger than its
   numeric score coverage.
4. After a new vehicle-down confirmation, record moving, loop-closure and
   relocalization datasets and decide whether RTAB-Map can graduate beyond the
   shadow baseline.
5. Address the existing Rerun coordinator graceful-stop timeout separately.
6. Do not enable motion or restore LD19.

## Open Questions

- Can Aurora depth coverage and synchronization meet RGB-D/VIO prerequisites?
- Can RTAB-Map produce navigation-usable map coverage after the camera can move?
- Will the full DimOS shadow stack preserve at least 1GiB available memory in
  an extended Orin soak?
- Can the public candidate results be normalized enough to support a stronger
  SOTA comparison without mixing datasets, inputs and alignment methods?
