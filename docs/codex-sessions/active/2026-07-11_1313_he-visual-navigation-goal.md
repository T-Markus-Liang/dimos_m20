# HE Visual Navigation Goal

## Metadata

- Date: 2026-07-11 13:13 CST
- Session id: current Codex goal thread
- Project: dimos-wd-m20
- Workspace: VM `/home/markus/work/dimos_wd_m20`; Orin `/home/ubuntu/he/dimos_wd_m20`
- Task: research, benchmark, select and integrate a visual SLAM navigation foundation for HE
- Status: active - shadow integrated; benchmark/extrinsics audit complete;
  physical calibration and moving gates pending
- Branch if relevant: `codex/he-orin`; documentation update based on `87549530`

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
- Re-audited VM, origin and Orin at `87549530`; both worktrees were clean,
  `he-dimos-sense` was active with zero restarts, no SLAM process remained and
  `/he/nav_cmd_vel` had zero publishers.
- Extracted directly scoped numeric evidence from the official ORB-SLAM3,
  OpenVINS, DPVO, DROID-SLAM, DPV-SLAM and MASt3R-SLAM papers. Added dataset,
  input, alignment, FPS, memory and hardware boundaries without constructing a
  cross-dataset ranking.
- Scanned the latest ScaRF-SLAM, GeoGS-SLAM and WildPose work. ScaRF is a
  GPL-3.0 learned mapping wrapper around classical tracking; the other two did
  not expose auditable official code during inspection. None replaces the HE
  shadow baseline.
- Audited the live HE static tree and source URDF. Aurora RGB-depth calibration
  is device-derived, while base-camera, base-IMU and composed camera-IMU values
  are nominal URDF/service transforms only. Physical camera-IMU qualification
  remains an explicit VIO gate.
- Verified the documentation update with all 29 HE unit tests, the generated
  blueprint registry test, `git diff --check` and required-file integrity.
- During the post-sync closeout, traced an intermittent stale-RGB failure to
  `verify-he-sensors.py` checking the first collected samples after waiting for
  slower endpoints. Changed every bounded stream to evaluate its latest N
  samples; a genuinely stopped stream still fails on its newest timestamp.
- Traced the remaining closeout termination to redundant repeated ROS CLI graph
  polling after temporary nodes had shut down. Replaced it with a two-second
  DDS settle; the existing final read-only gate remains the authoritative and
  stricter endpoint, process, command and port check.
- Added a non-suppressing `ERR` trap to the read-only gate so the still-failing
  final invocation reports the exact assertion instead of ending silently.
- Proved the missing closeout tail was a `systemd-run --pipe` output-channel
  artifact. The exact repository script completed in non-piped transient unit
  `he-static-final-1635` with `Result=success`, `ExecMainCode=0` and
  `ExecMainStatus=0`; final motion and service gates remained closed/healthy.
- Audited the live Aurora930 0.2.11 driver and SDK 1.1.22 source. Confirmed that
  `slam_mode`, mToF/sToF crop/filter and fusion/scatter settings are shared
  declarations but are not applied by the Aurora930 device path.
- Identified the Aurora-effective controls: remove-filter threshold, depth
  range, alignment, depth correction, laser mode, resolution and RGB-D stream
  selection. The driver reads them at construction and has no dynamic parameter
  callback, so future A/B tests require an isolated restart rather than
  `ros2 param set` alone.
- Extended the bounded Aurora diagnostic with depth value classes, per-row and
  per-column coverage, validity bounding boxes, temporal stability, the largest
  stable connected region, depth/IR correlation and point-cloud XYZ quality.
- Added four focused tests. All 33 HE unit tests pass, including under
  `-W error`; Ruff and `git diff --check` pass on the modified files.
- Pushed `673be17f` and fast-forwarded Orin to it. The enhanced 30-frame live
  baseline completed between read-only gates with no configuration change.
- Baseline depth was 24.26% valid and 75.74% zero; below-range, above-range and
  `65535` ratios were all zero. Point-cloud usable and zero XYZ ratios matched
  depth exactly, and all XYZ values were finite.
- Across 39 depth frames, 69.88% of pixels were never valid, 18.97% were always
  valid and only 11.15% were intermittent. The 90%-stable mask covered 20.84%
  of the image, but its largest connected region covered only 5.27%. This is a
  stable spatial-coverage defect rather than ordinary random frame loss.
- Added a restore-guarded Aurora A/B runner that accepts one effective parameter,
  owns the temporary process group, restores systemd on every exit path and
  reruns live sensor/read-only gates.
- The first runner invocation exited before installing the trap or stopping the
  service because ROS 2 `setup.bash` is not nounset-safe. Scoped `set +u` to the
  two environment sources and immediately restored `set -u`; no camera state or
  parameter changed during the failed invocation.
- The first complete threshold experiment restored both services, but the
  immediate read-only gate observed the temporary Aurora DDS publisher before
  endpoint expiry. The unchanged gate passed after three more seconds.
- Fixed the runner to wait five seconds for DDS convergence and to preserve
  `errexit` after restoration. Sensor/read-only failures can no longer fall
  through to a success message.
- `threshold_size=30` reduced global/center validity from 24.26/18.57% to
  21.84/15.66% and increased never-valid pixels to 72.37%; keep 110.
- `laser_power=2` produced 26.66% global, 18.95% center and 24.02% stable
  coverage, but requires an isolated `laser_power=1` control before attribution
  because both temporary runs observed point cloud near 8Hz.
- Completed the isolated auto-laser control: indoor versus auto differed by
  only 0.17 points global, 0.05 center and 0.07 stable, so mode 2 has no proven
  benefit and mode 1 remains canonical.
- Disabling alignment produced 25.65% global, 19.90% center and 23.23% stable
  coverage but retained the lower-image defect and removes required RGB-depth
  geometry. Keep alignment enabled.
- Disabling depth correction produced 26.46% global, 18.86% center and 23.79%
  stable coverage, effectively equal to its isolated control, while shifting
  depth p50/p95 without ground truth. Keep correction enabled.
- Reconfirmed every canonical runtime parameter, both services active with zero
  restarts, the live sensor gate and read-only gate. No tested setting was
  persisted and `/he/nav_cmd_vel` remained at zero publishers.
- Confirmed Aurora is on USB path `1-2.4`, a 480Mbps USB 2.0 hub shared with
  serial, audio and other devices; the 10Gbps root hub has no child. Kernel logs
  contain no reset, stall, overflow or bandwidth error and runtime power is
  active. This is a throughput risk but does not by itself explain a fixed mask.
- Added opt-in bounded RGB/IR/depth/valid-mask snapshot output to the diagnostic.
  The pure writer preserves uint16 millimetre depth and is covered by focused
  shape, padding, mask and metadata tests; default runs still write no images.
- Deployed and ran the snapshot diagnostic between read-only gates. RGB/IR were
  complete and no vehicle part or bracket occluded the lower frame. Upper-half
  depth was 48.69% valid versus 7.51% lower-half and 6.73% bottom-third.
- Visually, valid depth follows upright cabinets, doors, window structure and
  table legs, while the missing region follows a smooth dark floor seen at a
  grazing angle from the very low, near-level camera. Lower IR mean was higher,
  not absent. Scene/material geometry is now the leading hypothesis.
- Preserved only derived metrics and hashes in Git because RGB shows a private
  indoor scene. Raw snapshots remain in Orin `/tmp/he-aurora-field-of-view` and
  the host temporary evidence directory.
- Confirmed the shared USB 2 topology has no kernel reset/stall/overflow errors.
  Treat it as throughput risk requiring a paired USB 3 test, not as proof of the
  stable mask's cause.
- Audited and visually rendered relevant pages of the vendor Aurora900 SDK Guide
  V1.7. It confirms current API semantics but publishes no Aurora930 FOV,
  reflectivity, accuracy, grazing-angle, USB or mounting specification.
- Corrected a documentation assumption: 150-4000mm is the configured
  `FilterOutRangeDepthMap` window, not proven hardware rated range. The SDK has
  unexposed `SupportedInfo.depth_range`, edge trim, temperature and laser-current
  calls that the ROS driver does not surface; no undocumented direct SDK change
  is approved.
- Completed a 600-second full shadow soak with no motion publisher. Available
  memory stayed above 3.1GiB, full-stack RSS was about 1.82-1.84GiB, CPU was
  132-147%, GPU 6-23%, peak temperature 64.25C and swap grew only 3.75MiB.
- The 90-second stationary odometry sample had 4.72/8.25mm final/max drift but
  accumulated 0.480m frame-to-frame jitter. The active RTAB-Map database grew
  from 16.7MiB to 126.7MiB in 590 seconds, proving that file-count retention did
  not bound one running database.
- Added native 0.02m/0.01rad graph commit thresholds and a separately testable
  active-database watchdog. It defaults to 256MiB, rejects invalid boundaries
  before startup and makes the runner clean up all native children at the cap.
- Preserved the primary/supplement TSV and 90-second odometry JSON under
  `docs/he/evidence/2026-07-11_20*`. All 38 HE tests, Ruff, Bash syntax and
  `git diff --check` pass on the VM; Orin post-deployment soak is pending.

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
- Do not test shared Nebula/Stellar parameters against Aurora930 merely because
  the ROS node declares them. Limit controlled depth A/B tests to settings that
  the Aurora930 configure path actually applies.

## Current State

- VM has the tested database-boundedness patch and baseline evidence pending
  commit. Origin and Orin remain on the preceding clean commit until this
  change is pushed and fast-forwarded. Use `git rev-parse HEAD` for commit
  identity rather than embedding a self-invalidating value here.
- The final current-script static closeout passed under systemd with status 0.
  `he-dimos-sense` is active with zero restarts, memory is about 1005MiB,
  no visual SLAM node is running and `/he/nav_cmd_vel` has zero publishers.
- The final static closeout passed all 29 pre-diagnostic HE tests, blueprint
  discovery,
  deployment integrity, isolated control dry-run, Aurora live quality and both
  read-only gates. `he-dimos-sense` is active with zero restarts.
- DimOS visual shadow modules, lifecycle controls, ADR and evidence are
  committed, pushed and exercised on Orin. Current map quality remains
  unhealthy and no planner costmap or motion command is released.
- Aurora depth coverage, camera extrinsics, moving accuracy, loop closure and
  relocalization remain open gates. Real motion remains prohibited.
- The enhanced diagnostic and effective-parameter A/B are complete. No tested
  setting resolves the stable spatial defect, so the canonical configuration is
  restored and RGB-D navigation admission remains failed.
- The extended static soak is complete and exposed active-database growth as a
  real defect. The boundedness patch is implemented and unit-tested on the VM,
  but remains pending deployment and a second 600-second Orin soak.

## Resume Instructions

1. Read this log, ADR-001 and the final shadow soak evidence.
2. Deploy the database boundedness patch and repeat the 600-second stationary
   shadow soak; compare database slope, RSS, CPU, GPU, swap and cleanup gates.
3. Run a static matte-target and camera pitch/height experiment to separate
   floor reflectivity/grazing-angle effects from sensor defects.
4. Evaluate a controlled move from the shared USB 2.0 hub to the available
   10Gbps root port if physical access is approved.
5. Escalate firmware 2.0.8/SDK 1.1.22 evidence to the vendor if target coverage
   remains abnormal, requesting optical specifications and the documented
   `SupportedInfo.depth_range` interpretation.
6. Use the new nominal-extrinsics audit to plan physical camera-to-base and
   camera-to-IMU calibration; do not promote the nominal values to calibrated.
7. Keep public benchmark tables source-scoped and update them only when a new
   candidate has code, license, runtime and deployability evidence.
8. After a new vehicle-down confirmation, record moving, loop-closure and
   relocalization datasets and decide whether RTAB-Map can graduate beyond the
   shadow baseline.
9. Address the existing Rerun coordinator graceful-stop timeout separately.
10. Do not enable motion or restore LD19.

## Open Questions

- Can Aurora depth coverage and synchronization meet RGB-D/VIO prerequisites?
- Can RTAB-Map produce navigation-usable map coverage after the camera can move?
- Will the full DimOS shadow stack preserve at least 1GiB available memory in
  an extended Orin soak?
- Can the public candidate results be normalized enough to support a stronger
  SOTA comparison without mixing datasets, inputs and alignment methods?
