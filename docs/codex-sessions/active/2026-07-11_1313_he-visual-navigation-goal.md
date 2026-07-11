# HE Visual Navigation Goal

## Metadata

- Date: 2026-07-11 13:13 CST
- Session id: current Codex goal thread
- Project: dimos-wd-m20
- Workspace: VM `/home/markus/work/dimos_wd_m20`; Orin `/home/ubuntu/he/dimos_wd_m20`
- Task: research, benchmark, select and integrate a visual SLAM navigation foundation for HE
- Status: active - static dual-path shadow and resource gates qualified;
  physical calibration, service isolation and moving gates pending
- Branch if relevant: `codex/he-orin`; use `git rev-parse HEAD` for current identity

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
- The first deployed threshold test failed its slope objective: the database
  reached 33.1MiB at 121 seconds. RTAB-Map 0.23.7 source confirms rehearsal
  precedes its default 0.1m/0.1rad motion gate and unlinked nodes are persisted
  by default. Restore 0.1/0.1 and set `Mem/NotLinkedNodesKept=false`; the hard
  watchdog remains unchanged. A detached rerun is pending.
- Completed the corrected detached 600-second soak. The active database gained
  1.06MiB in 590 sampled seconds versus about 110.0MiB before the fix, reducing
  stationary growth about 99.0%. Swap growth was zero; full-stack RSS averaged
  1.73GiB and peaked at 1.77GiB; CPU averaged 134%, GPU averaged 11% and peaked
  at 26%; maximum temperature was 63.28C.
- Preserved the corrected primary and supplement TSV evidence. Every sampled
  navigation publisher count was zero. After DDS endpoint convergence, the
  independent read-only gate passed with both services active, zero restarts
  and no native SLAM process.
- Recorded two orchestration hazards and fixes: redirect native output for
  detached soaks to avoid SSH SIGPIPE 141, and require exactly one timer/restore
  owner so an old soak cannot stop a new run.
- Re-audited timestamped worker shutdown logs and corrected the prior Rerun
  attribution. Rerun stopped in about 73ms; the RTAB-Map shell cleanup could
  spend about 7.5 seconds polling three unreaped zombies with `kill -0`.
- Replaced serial zombie polling with a shared two-second signal escalation and
  final `wait`, made external SIGINT/SIGTERM return success, and reduced the
  Python process-group fallback to three seconds. A real process-group lifecycle
  test raises the HE total to 39; all pass with Ruff and Bash checks on the VM.
- The first normal-stop Orin attempt still escalated after 7.099 seconds. Logs
  show the coordinator waited five seconds for the Rerun stop RPC, while direct
  worker shutdown stopped Rerun in about 1.2ms after parent escalation.
- Reordered only the shadow blueprint lifecycle: Rerun starts first/stops last,
  and the native runner starts last/stops first. This cuts visual producers
  before bridge shutdown; a focused order assertion preserves the contract.
- The second normal stop still escalated after 6.971 seconds even though the
  native runner was stopped first. Core audit found `RpcCall.stop()` synchronously
  spent up to five seconds closing the caller's own LCM RPC backend after its
  `call_nowait` publication.
- Moved only caller-backend cleanup to a named daemon thread. A focused test
  proves stop returns under 100ms while cleanup starts and later terminates.
  Thirty-six related core lifecycle/CLI tests and all 39 HE tests pass on VM.
- The third Orin normal stop reported `Stopped with SIGTERM` in 4926ms and left
  no native process or Rerun port. It still logged six
  `can only join a child process` errors, so it is not a clean pass.
- Confirmed workers are created before the daemon double fork. The daemon is
  not the `multiprocessing.Process` parent and cannot call `join()`. Added a
  parent-aware wait that retains `multiprocessing.join()` in the original
  parent and uses `psutil.Process(pid).wait()` in the daemon/non-parent.
- Made registry liveness zombie-aware and gave the asynchronous RPC cleanup
  thread a bounded 100ms join. Forty-nine related core tests, 39 HE tests,
  Ruff and `git diff --check` pass on the VM; clean Orin lifecycle proof is
  pending.
- The fourth Orin attempt removed the assertion and started visual odometry
  with zero navigation publishers, but normal stop took 7111ms and escalated.
  Logs prove the first full stop completed in about 2.45 seconds; a pre-exit
  tagged-process sweep then waited two seconds on multiprocessing helpers, and
  loop unwinding invoked coordinator stop a second time.
- Removed only the redundant signal-handler sweep because the independent
  post-exit watchdog retains orphan cleanup. Made coordinator stop lock-protected
  and idempotent. Fifty related core tests, 39 HE tests and static checks pass
  on VM; the fifth clean Orin lifecycle attempt is pending.
- The fifth Orin attempt passed functionally: CLI reported normal SIGTERM stop,
  logs had one shutdown round and no errors, and no process or port remained.
  End-to-end CLI time was still 5228ms even though coordinator cleanup finished
  in about 2.52 seconds.
- Reduced the per-module asynchronous RPC cleanup observation from 100ms to
  10ms, removing about 0.45 seconds of cumulative delay while retaining a
  bounded immediate-cleanup opportunity. Fifty core tests, 39 HE tests and
  static checks pass; the sixth Orin timing run is pending.
- The sixth Orin run completed the shutdown gate. CLI reported
  `Stopped with SIGTERM`; source inspection confirms this means exit inside the
  five-second post-signal loop. The 5500ms outer measurement included CLI cold
  start before signal delivery.
- The final log had five module stops, one worker shutdown round and no errors
  or SIGKILL. No process or port remained. Restored `he-dimos-sense` active with
  zero restarts; live sensor quality and independent read-only gates passed,
  with zero navigation publishers.
- Audited the remaining map persistence gap. The runner previously treated an
  explicit old database as incremental mapping, preserving the known graph
  fatal risk after visual odometry reset.
- Added explicit `mapping` and `localization` contracts. Mapping refuses an
  existing explicit database. Localization requires an existing non-empty
  readable database and forces non-incremental, all-nodes, read-only operation
  without saving localization data.
- Added a ROS-independent mode validator and fail-closed tests for invalid
  modes, missing/empty localization databases and unsafe mapping reuse. All 40
  HE tests, Ruff, Bash syntax and `git diff --check` pass on the VM; Orin static
  map creation and same-scene read-only reload are pending.
- The first Orin mapping launch rejected the overrides before map creation:
  RTAB-Map declares `Mem/*` ROS parameters as strings, while the new argv used
  bool scalars. The wrapper raised `InvalidParameterTypeException`; DimOS and
  native children stopped normally, the sensor service was restored, and no
  mapping database or motion publisher remained.
- Confirmed with a bounded native 0.23.7 probe that explicitly quoted YAML
  string scalars are accepted and enter SLAM mode. Updated all mode overrides
  and tests to preserve the quotes. All 40 HE tests and static checks pass again;
  clean Orin mapping/localization rerun is pending.
- The corrected mapping run created a 659456-byte RTAB-Map 0.23.7 database with
  one Node, 149 Statistics rows and `integrity_check=ok`. Thirty-second odometry
  ran at 5.65Hz with zero losses; the 83x60 map remained unhealthy at 2.851%
  known space.
- Loaded the same database in read-only localization mode. RTAB-Map restored
  saved map correction against node 1, reported a good localization candidate,
  emitted the identical map plus pose/TF, and had zero tracking loss over the
  30-second benchmark.
- Database size, mtime and SHA-256 stayed identical before, during and after
  localization and normal shutdown. No graph fatal, process or port remained.
  Restored `he-dimos-sense` active with zero restarts; live sensor and read-only
  gates passed with zero navigation publishers.
- Preserved four benchmark JSON files and the qualification report under
  `docs/he/evidence/2026-07-11_2237_*`. Same-scene map loading is proven;
  moving/displaced-start relocalization remains gated.
- Tightened localization admission after review: non-empty was too weak because
  any file could reach RTAB-Map. The runner now opens SQLite read-only and
  requires the core `Admin/Data/Info/Node` schema before launch. Tests cover
  malformed SQLite and missing-schema files; all 40 HE tests still pass.
- Added a bounded, read-only `/localization_health` pLCM benchmark that records
  every sample, reason counts, maximum pose/map/TF ages and state transitions.
  Added a pure summary test covering baseline -> stale-input fault -> baseline
  recovery. All 41 HE tests, Ruff and `git diff --check` pass on the VM; live
  Aurora outage/recovery fault injection is pending.
- Deployed the health observer on Orin. The independent eight-second baseline
  captured 135 samples with only `map_known_ratio_low`, maximum 0.368s pose age
  and 0.510s TF age.
- Injected a 7.014s Aurora service outage under a restore trap. `pose_stale`
  appeared 0.459s after inactive, `tf_stale` at 1.032s and `tf_unavailable` at
  5.031s. The original baseline returned 3.994s after service activation.
- A separate five-second recovery run captured 84 baseline-only samples.
  After startup convergence, Aurora returned to about 14Hz with valid point
  cloud and 28.1% depth coverage. Shadow stopped normally; both services,
  sensor quality, read-only safety and zero navigation publishers were restored.
- Preserved bounded baseline, event, fault/recovery and post-recovery JSON plus
  `docs/he/evidence/2026-07-11_2345_visual-input-outage.md`. Total input-loss
  freshness detection is proven; partial/bad-but-fresh and moving tracking loss
  remain open.
- Audited the raw HE IMU and official RTAB-Map 0.23.7 source. The raw topic is
  about 47Hz and carries gyro/acceleration, but every sampled orientation is an
  all-zero quaternion that RTAB-Map explicitly ignores.
- Confirmed Orin already has `imu_filter_madgwick` 2.1.5. A bounded isolated
  probe with no magnetometer and no TF produced a normalized orientation at
  about 46.7Hz without changing services or motion state. Its orientation
  covariance remained all zero and yaw is gyro-integrated, so this is not proof
  of calibrated VIO.
- Added a pure IMU metrics helper and bounded ROS diagnostic for raw/filtered
  rates, timestamp gaps, quaternion validity, RPY drift, gyro/acceleration
  statistics and covariance state. Focused tests initially raised the HE total to 43;
  Ruff and `git diff --check` pass on the VM.
- Reconfirmed both system services active with zero restarts, no probe process
  or topic left behind and `/he/nav_cmd_vel` at zero publishers.
- The first 30-second Orin diagnostic reached JSON rendering but exposed ROS
  covariance comparison counts as NumPy `int64`, which standard `json` rejects.
  The exit trap removed the probe and all safety checks remained closed/healthy.
  Explicitly normalized count fields to Python `int` and added a NumPy-backed
  `json.dumps` regression test. All 44 HE tests and Ruff pass on the VM; the
  corrected Orin evidence run was then completed.
- The corrected 30-second static comparison measured raw/filtered rates near
  46.56Hz. Filtered orientation was normalized but drifted 1.207deg final and
  1.218deg maximum; yaw changed -1.187deg. Static gyro x mean was 0.03327rad/s,
  acceleration norm median was 9.9910m/s2, and all 1394 filtered orientation
  covariance samples were zero.
- Preserved the raw JSON and qualification report under
  `docs/he/evidence/2026-07-12_0024_imu-qualification.*`. The immediate cleanup
  check observed the native process during its SIGTERM exit race; the next
  bounded check confirmed no process/topic remained. Live sensor and read-only
  gates passed, services remained active with zero restarts, and navigation
  publishers remained zero.
- Started the next motion-free gap: bad-but-fresh visual input faults. Added
  fail-closed RTAB-Map input topic overrides and a bounded proxy that publishes
  baseline, blank fault and recovery phases only on isolated `/he/fault/*`
  topics. Default Aurora inputs remain unchanged.
- Deployed the proxy at `0e3ef1bc` and ran read-only blank RGB and blank depth
  localization faults. Blank RGB added pose stale in 0.248s, tracking lost/low
  inliers in 0.694s and TF stale in 0.853s; recovery restored the original
  map-quality-only baseline in 0.451s.
- Blank depth added pose stale in 0.477s and TF stale in 1.012s, then restored
  the baseline in 0.440s. RTAB-Map did not emit a new explicit lost/inlier
  status, so depth failure is caught by pose/TF freshness. Both database hashes
  remained unchanged.
- Preserved four raw JSON files and
  `docs/he/evidence/2026-07-12_0041_fresh-visual-faults.md`. Final live sensor
  and read-only gates passed at about 980MiB bridge memory; services were active
  with zero restarts and navigation publishers remained zero.
- Extended the isolated proxy with `drop-camera-info`: RGB/depth remain fresh,
  only RGB CameraInfo is withheld in the fault phase, and received/published
  calibration counts are recorded.
- Deployed CameraInfo-only fault injection at `7c56a2e2`. During the fault,
  RGB/depth each published 43 images, RGB CameraInfo received 42 but published
  zero, and depth CameraInfo received/published 42. Pose stale appeared in
  0.316s, TF stale in 0.719s and the original baseline returned 0.244s after
  recovery. No explicit tracking/inlier reason appeared.
- Preserved the full health and proxy JSON plus
  `docs/he/evidence/2026-07-12_0052_camera-info-fault.md`. Database hash was
  unchanged; repeated sensor/read-only gates passed, services stayed at zero
  restarts and navigation publishers remained zero.
- Added direct RGB CameraInfo validation to the visual bridge and explicit
  missing/invalid/stale localization-health reasons. Added a
  `corrupt-camera-info` proxy mode that keeps publishing K/P with zero focal
  lengths. All 48 HE tests and Ruff pass on the VM.
- On Orin, 41 zero-focal CameraInfo messages triggered `camera_info_invalid` in
  0.363s; the reason cleared 0.009s after recovery and the original baseline
  returned in 0.209s. The updated drop test triggered `camera_info_stale` in
  0.946s and cleared it 0.103s after recovery.
- Preserved four raw JSON files and
  `docs/he/evidence/2026-07-12_0107_camera-info-health-gate.md`. Both database
  hashes were unchanged. Final sensor/read-only gates passed at about 866MiB
  bridge memory, services had zero restarts and navigation publishers were zero.
- Added a versioned HE runtime intrinsic baseline with 2% focal and 2px
  principal-point tolerances, plus `shift-camera-intrinsics` fault injection.
  This detects runtime drift but does not claim physical calibration accuracy.
- Completed the isolated Orin intrinsic-drift proof. Thirty-one structurally
  valid RGB CameraInfo messages with 10% focal and 10px principal-point shifts
  triggered `camera_info_invalid` in 0.286s. The reason cleared 0.135s after
  recovery and the original baseline returned in 0.510s; TF freshness failed
  later at about 1.030s and became unavailable at about 5.083s.
- Preserved both raw JSON files and
  `docs/he/evidence/2026-07-12_0118_intrinsic-baseline-drift.md`. The database
  hash stayed unchanged, final sensor/read-only gates passed, services had zero
  restarts, bridge memory was about 822MiB, available memory was about 3.5GiB
  and navigation publishers remained zero.
- Closeout verification passed all 48 HE unit tests, focused Ruff checks for the
  CameraInfo/visual-SLAM implementation, machine-parsed both JSON files and
  asserted the 0.286/0.135/0.510s timeline, and passed `git diff --check`.
  A broad HE Ruff scan still reports eight pre-existing import-order findings
  in untouched connection, sensor and deployment files; they are not mixed into
  this evidence-only closeout.
- Committed and pushed the evidence closeout as `7cc9ab79`, fast-forwarded the
  Orin worktree, and synchronized the canonical deployment guide to the macOS
  Downloads mirror. Post-sync checks kept `HEConnection.enabled=False`, the
  sensor service active with zero restarts, no SLAM/fault process and zero
  `/he/nav_cmd_vel` publishers.
- Audited the live control-board IMU path. Firmware supplies six float values,
  the SDK applies no scaling, and the ROS driver converts g to m/s2 and deg/s to
  rad/s but has no bias, temperature, scale or axis calibration and publishes
  no sensor-model/range metadata. The static 0.033rad/s x mean is therefore not
  a missing ROS unit conversion.
- Extended the bounded IMU diagnostic with 60-second block-mean stability,
  non-overlapping Allan deviation at bounded cluster durations and the
  stationary gyro-mean integral. Added fail-closed input validation and two
  focused tests; the five IMU helper tests and focused Ruff pass on the VM.
  The initial 10-minute Orin static evidence run was then completed.
- Captured 27,918 raw samples across 598.022s at 46.682Hz with zero nonpositive
  timestamps and nine complete 60-second windows. Gyro x mean was
  0.032530rad/s (1.864deg/s), while the 60-second mean span was only
  0.000479rad/s; uncompensated mean integration was 1114.61deg.
- Preserved `docs/he/evidence/2026-07-12_0134_imu-static-stability.md` and raw
  JSON. The post-capture read-only gate passed, services had zero restarts,
  available memory remained about 3.2-3.3GiB and navigation publishers stayed
  zero. Raw IMU remains rejected for VIO; six-position, axis, temperature and
  physical camera-IMU calibration remain open.
- Evidence closeout passed all 50 HE unit tests, focused Ruff, JSON parsing and
  exact sample/duration/window/bias/hash assertions, plus `git diff --check`.
- Pushed the diagnostic implementation as `09efdd23` and the live evidence as
  `f760cc62`, fast-forwarded Orin after each, and synchronized the canonical
  deployment guide to the macOS Downloads mirror. The final Orin read-only gate
  passed at about 1005MiB sensor-bridge memory and 3.3GiB available memory with
  zero navigation publishers.
- Audited the Aurora900 SDK 1.1.22 support API and guide. `GetSupportInfo`
  exposes a vendor depth-range buffer, while temperature, laser-current,
  device-info and factory RGB/IR camera-parameter getters are also available.
  The depth-range ABI is opaque and must be preserved as length/hex/text before
  interpretation; it is not the known 150-4000mm software filter by definition.
- Added a minimal C++ getter-only probe and restore-guarded runner. It omits the
  serial number, creates no stream, invokes no setter/reboot/upgrade and reruns
  sensor/read-only gates after restoring the canonical service. Compilation
  against the real SDK headers with `-Werror`, Bash syntax and diff checks pass
  on the VM. All 50 HE tests and an explicit SDK method-call safety audit also
  pass; live Orin evidence is pending.
- The first Orin probe returned vendor depth range `0.3~1m`, 7x24 support,
  no synced-two-image support, raw camera/VCSEL/CPU temperatures 65/63/70 and
  1450mA laser current. This proves the configured 150-4000mm filter is not the
  device-rated range.
- `GetDeviceInfo` and `GetCameraParameters` returned `-1` because the SDK
  requires `SetMode`; the getter-only contract remains stricter and those
  outputs must be null. Fixed failed-getter serialization, moved SDK logs with
  serial data to exit-cleaned temporary files, and increased DDS convergence
  wait from five to ten seconds after the first final gate saw a stale endpoint.
  The EXIT-trap gate passed.
- The second run proved null serialization and temporary-log cleanup, but a
  fixed ten-second wait still saw a stale DDS publisher before the trap's later
  gate passed. Replaced fixed timing with up to six complete read-only-gate
  attempts at three-second intervals.
- The third probe passed its complete main path. Final SDK evidence repeated
  depth support `0.3~1m`, `synced_two_images=0`, 1450mA laser current and raw
  temperatures 65/63/72. Device-info/camera-parameter fields remained safely
  null, and no SDK log or probe binary remained.
- Preserved `docs/he/evidence/2026-07-12_0213_aurora-sdk-support-probe.md` and
  raw JSON. The device support range conflicts with live valid-depth p50/p95
  1240/2522mm, so vendor interpretation remains required; no algorithm cutoff
  was changed. Final sensor/read-only gates passed with zero service restarts,
  about 3.3GiB available memory and zero navigation publishers.
- Evidence closeout passed all 50 HE tests, C++ `-Werror` compilation against
  the real SDK headers, Bash syntax, JSON/hash/support-range/live-depth
  cross-assertions, serial-pattern exclusion and `git diff --check`.
- Began the HE Sense resource optimization from a clean three-way baseline at
  `725041e3`. The live cgroup was about 1001MiB: Rerun accounted for about
  559MiB private anonymous memory, HESensorBridge about 155MiB, the coordinator
  about 128MiB and two idle workers about 72MiB each; `/dev/shm` was not the
  dominant cost.
- Confirmed that dedicated modules intentionally trigger the global Python
  worker capacity policy from two configured workers to four total workers.
  This HE task will not change that shared policy. The first scoped A/B changes
  only the `he_sense_headless` Rerun recording window from 256MB to 128MB.
- Added pure procfs/cgroup parsers, focused unit tests and a one-shot read-only
  `profile-he-sense-memory.py` tool. It captures systemd limits, cgroup-v2
  counters, per-process PSS/private memory and largest anonymous mappings
  without restarting the service or reading sensor payloads. Ruff and two
  parser tests pass; a VM system-service smoke test confirmed that cross-user
  `smaps` access correctly requires `sudo`. The final root smoke read the live
  `ssh.service` cgroup successfully; all 52 HE `unittest` cases, focused Ruff
  and `git diff --check` passed. The repository-wide pytest wrapper reports
  teardown errors from its global thread monitor for pre-existing HE LCM daemon
  threads even though all 52 assertions pass, so the established HE unittest
  entry point remains the canonical result for this scoped change.
- The profiler landed as `770a967a`, was pushed and fast-forwarded cleanly to
  Orin. The pre-baseline read-only gate passed with the existing 256MB service,
  zero restarts and zero navigation publishers.
- Captured 11 identical profiler snapshots from 02:30:31 through 02:40:36 CST
  without restarting the service. Cgroup memory min/median/max was
  1047842816/1050038272/1055834112 bytes. Rerun worker median PSS/private dirty
  was 595964928/570478592 bytes; HESensorBridge median PSS was 172328960 bytes.
  Available-memory median was about 3.30GiB, swap did not grow and restarts
  remained zero.
- The 256MB post-gates passed: RGB 15.62Hz, depth 10.10Hz with 25.7% validity,
  IR 16.13Hz, 256000-point cloud and both calibrations. The Rerun `9877` port
  was reachable from macOS and `/he/nav_cmd_vel` still had zero publishers.
- Prepared the scoped 128MB change only in `he_sense_headless`. A new structural
  regression test locks the two-module surface, eight latest-only entities and
  all default sensor modalities. All 53 HE unittests, focused Ruff, blueprint
  registry generation and diff checks passed on VM; Orin had not yet restarted
  onto this setting at this log update.
- Committed the scoped setting and baseline snapshot as `40c563a5`, pushed it,
  fast-forwarded Orin and restarted only `he-dimos-sense.service`. The new main
  PID became 201141, port 9877 recovered, service restarts remained zero and
  the immediate live sensor/read-only gates passed.
- Completed 11 candidate snapshots from 02:48:59 through 02:59:24 CST. Median
  cgroup memory fell by 130.895MiB (13.1%) to 870.500MiB; maximum fell to
  872.691MiB, leaving 151.309MiB below `MemoryHigh`. Rerun worker median PSS
  fell by 178.117MiB and its largest anonymous mapping by 188.082MiB. Both A/B
  runs had zero swap growth and zero service restarts.
- A 60-point-cloud-sample post-run diagnostic measured RGB/depth/IR/point
  cloud/IMU at 14.599/14.286/14.925/13.333/46.820Hz, with 25.941% median depth
  validity and both calibrations present. Port 9877 remained reachable from
  macOS and the isolated final read-only gate passed with zero navigation
  publishers.
- One combined diagnostic command triggered a read-only false positive because
  its own later pgrep arguments contained forbidden process names. Re-running
  the gate alone passed and confirmed no localization/navigation process.
- Preserved the candidate snapshot, extended Aurora diagnostic and A/B report
  in `a2cd5879`, pushed the evidence commit and fast-forwarded Orin without a
  service restart because that commit changed documentation only. The final
  closeout audit retains the running 128MB process, zero restarts, remote port
  availability and closed motion gate.
- Audited the shadow resource-health contract after the HE Sense memory
  closeout. Existing health correctly bounded RTAB-Map process-group RSS, but
  did not reject stale runtime evidence, treated missing/NaN RSS as zero, and
  did not carry the goal's 1GiB available-memory or no-sustained-swap evidence.
- Extended the existing runner status without adding a module or dependency:
  it now reports system available memory, swap used and swap growth relative to
  runner startup. Health defaults fail closed at 2.5s status age, 768MB RSS,
  1GiB available memory and 64MB swap growth, with distinct invalid/high/low
  reasons and resource values retained in details.
- Added procfs parser, resource fault/recovery, missing-field and summary-age
  tests. All 24 visual-SLAM and 56 HE unittest cases, focused Ruff and diff
  checks passed on VM. Orin deployment and real static shadow evidence remain
  pending at this log update.
- Committed and pushed resource health as `bf5f8215`, then fast-forwarded Orin
  after a clean pre-deployment read-only gate. A first concurrent start failed
  before native SLAM because the active Sense coordinator already owns the
  host-global Coordinator RPC; no database, OOM or navigation residue resulted.
- Re-ran under one EXIT restore trap with Sense stopped. The forced 8GiB
  available threshold produced `system_memory_low` in all 184 health samples.
  A second fresh run at the 1GiB default cleared that reason in all 187 samples
  and retained only `map_known_ratio_low`.
- Real runtime values were valid and fresh: process-group RSS about 434-435MB,
  system available about 3.29-3.30GiB, swap used 548.523MB, swap growth zero and
  maximum status age about 1.08s. Both runs stopped with ordinary SIGTERM and
  left no native process or error log.
- The restore trap restarted `he-dimos-sense`; final RGB/depth/IR were
  15.50/10.26/15.62Hz, point cloud had 256000 points, calibrations were present,
  service restarts remained zero and the independent read-only gate passed.
- Chose a scoped response to the host-global Coordinator constraint instead of
  changing core RPC behavior: add `HESensorBridge` directly to
  `he_visual_slam_shadow`. One coordinator can then run native full-rate ROS
  SLAM and sampled latest-only Rerun sensor visualization simultaneously while
  the standalone Sense service is stopped under the existing restore trap.
- Expanded the shadow Rerun surface from six visual entities to fourteen total
  sensor and visual entities, retaining the 256MB bound. Structural tests lock
  HESensorBridge presence, exact entity order and absence of all motion modules.
  All 24 visual-SLAM and 56 HE tests, Ruff, blueprint registry and diff checks
  pass on VM; combined Orin resource qualification is pending.
- Deployed the first combined shadow as `a6053859` and completed an 11-point,
  10-minute static soak. All eight sampled outputs persisted while native SLAM
  ran, every navigation-publisher sample stayed zero and temperature peaked at
  66.375C. A process-tree profiler based only on parentage missed daemonized
  workers; a short tagged-process rerun correctly found 14 processes and about
  1.43GiB total PSS.
- The first candidate failed resource admission despite at least 2.56GiB
  available memory: runner-relative swap growth reached 84.25MiB and all 251
  final health samples reported `swap_growth_high`. The restore trap stopped
  shadow normally and restored Sense; this configuration is not accepted.
- Prepared a scoped second candidate: make only the lightweight native runner
  manager non-dedicated, reducing expected workers from eight to six, and use
  the previously qualified 128MB sensor Rerun window for the 14 latest-only
  entities. Global worker policy and the three CPU/data-heavy dedicated modules
  remain unchanged. VM 56-test, Ruff, registry and diff checks pass; Orin A/B
  remains pending.
- Deployed the optimized candidate as `9c1588d0` and repeated the full
  11-point/10-minute soak with process discovery corrected to use run tags at
  every sample. Worker logs confirmed six total workers; 13 tagged processes
  stayed stable with 1.31GiB median and 1.32GiB maximum PSS.
- The optimized run passed resource admission: available memory never fell
  below 2.85GiB, main-loop and runner-relative swap growth were both zero,
  native RSS ended at 430.81MB, runtime age stayed below 1.083s and temperature
  peaked at 66.75C. No resource reason appeared in 259 health samples.
- All eight sampled streams persisted from start to end while native SLAM ran.
  Three health samples briefly added `pose_stale` at a 0.531s maximum and
  recovered automatically; the 0.5s threshold remains unchanged. Every system
  sample had zero navigation publishers.
- Optimized shadow stopped with ordinary SIGTERM and no error/native residue.
  Sense restoration, live sensor gate, final read-only gate and remote port
  9877 connectivity all passed with zero service restarts.
- Preserved the failed-v1 and passing-v2 comparison, full v2 health/runtime and
  static soak report in `832e842f`, pushed the evidence and fast-forwarded Orin.
  The running state remains the restored Sense service; no shadow or navigation
  process is left active.
- Added a static `he-dimos-shadow.service` and reciprocal conflict with the
  enabled Sense service so the two host-global coordinators cannot run
  concurrently. The shadow cgroup is bounded at 2GiB high/2.5GiB maximum,
  `OOMPolicy=stop` and 512 tasks; it runs foreground with no restart policy.
- Added a single mode switch and shadow-specific read-only gate. Failed shadow
  startup/admission restores Sense automatically, normal return reruns the
  existing read-only gate, and no force-stop path is exposed. VM validation
  passed 25 visual-SLAM and 50 focused HE tests, unit verification, shell syntax
  and diff checks; Orin installation and service-level soak remain pending.
- The first service-level Orin return to Sense exposed a readiness race:
  systemd was active before the sensor worker registered every ROS subscriber.
  The unchanged gate passed seconds later. Refactored both mode admissions to a
  bounded six-attempt/five-second readiness loop and added structural coverage;
  timeout still fails and shadow-error restoration still returns to Sense.
- Installed the shadow unit and completed a service-level 10-minute Orin soak.
  Eleven samples held cgroup memory at 1346.7-1366.7MiB and tasks at 349;
  available memory stayed above 3011.9MiB, swap did not grow, and high/max/OOM,
  restarts and navigation publishers stayed zero. Journal warnings were empty
  and the final shadow gate passed.
- Deployed readiness fix `951d1108` and passed a complete
  `Sense -> shadow -> Sense` round trip. Normal stop left no native residue and
  final deployment integrity/read-only gates passed with Sense enabled/active,
  shadow static/inactive, and zero navigation publishers. Evidence and profiler
  snapshots are in `docs/he/evidence/2026-07-12_0448_shadow-systemd-cgroup.md`.
- Added a bounded long-duration visual timing diagnostic for RGB, depth, IR,
  point cloud and IMU. It retains only source/receipt timestamps, caps each
  stream at 200,000 samples, rejects any navigation publisher, and reports
  interval jitter, regressions/duplicates, estimated drops, callback age and
  RGB-nearest cross-stream alignment. This avoids the payload retention in the
  short depth-quality diagnostic. All 59 HE tests, Ruff, registry and diff
  checks pass on VM; Orin timing evidence remains pending.
- The first 10-minute timing run showed that median period alone masks
  intermittent whole-frame gaps. Added full-window source/receipt rates,
  sampling spans and estimated missing ratios, and now records actual monotonic
  duration. The unchanged payload-free collector remains bounded; a paired
  Sense-concurrent versus isolated-subscriber A/B is required before assigning
  the gaps to Aurora/USB rather than diagnostic subscription pressure.
- Completed a 600-second bounded timing run and paired 120-second subscriber
  A/B. The diagnostic ended at 102.9MiB RSS with stable Sense/system memory,
  zero swap growth/restarts/navigation publishers, and no timestamp regressions
  or duplicates. RGB/depth/IR/point-cloud estimated missing ratios were about
  7.0/16.5/6.8/34.7% over ten minutes.
- Stopping Sense reduced depth/point-cloud missing ratios from 10.8/34.0% to
  1.6/16.1%, proving bridge-side contention is material while leaving a
  separate USB2/driver limitation. Exact RGB pairing was not universal, so
  hardware synchronization remains unclaimed and admission remains failed.
- Tested and rejected the two-thread point-cloud callback candidate: depth and
  point-cloud missing ratios worsened to 14.6/37.1% and point-cloud alignment
  P95 worsened to 124ms. Reverted to the qualified single-thread implementation;
  Orin post-revert deployment passed deployment integrity, read-only and live
  sensor gates. Sense is active with zero restarts, shadow is inactive, all
  Aurora modalities/calibrations are present and navigation publishers are zero.
- Audited ROS Humble `topic_tools` 1.1.2 and confirmed its native throttle uses
  GenericSubscription/GenericPublisher over SerializedMessage. Installed the
  official Apache-2.0 arm64 package and proved a temporary 1Hz relay preserves
  the 256000-point, 4096000-byte PointCloud2 payload. Manual cleanup also proved
  the `ros2 run` wrapper can leave its native child, so deployment directly execs
  the binary under a systemd cgroup.
- Prepared a Python-before-deserialization candidate: raw point cloud remains
  available for local algorithms, a bounded native service publishes a 1Hz
  sampled topic, and HESensorBridge consumes only that sampled topic. Sense,
  shadow, integrity and both read-only gates lock service and graph ownership.
  All 60 HE tests and static checks pass; Orin A/B is pending.
- Pushed the probe, failed-getter fix, bounded DDS convergence and final
  evidence as `1655079a`, `b7b56853`, `a4af65e6` and `64cfeb4c`; Orin
  fast-forwarded cleanly and the macOS deployment mirror was synchronized.
  The final repository-version read-only gate passed at about 1001MiB sensor
  bridge memory and 3.3GiB available memory with zero navigation publishers.
- Deployed native serialized pre-throttling candidate `0a4db838`. A canonical
  1.0Hz 75-second sample reproduced 0.863Hz effective output with a 3.057s
  maximum interval; an adjacent temporary 1.2Hz sample produced 0.993Hz with a
  2.652s maximum interval. Selected 1.2Hz upstream with a 1.3Hz Python guard so
  Rerun receives about 1Hz despite raw USB/driver gaps. VM validation passed all
  60 HE tests, Ruff, blueprint registry, shell syntax, systemd verification and
  diff checks. Final Orin 120-second timing/resource and shadow round trip remain
  pending; Sense is active and the canonical 1.0Hz service was restored meanwhile.
- Committed and deployed the selected 1.2Hz/1.3Hz limits as `eee19da2`. A final
  125-second sampled run delivered 1.014Hz with a 2.648s maximum interval. The
  following raw timing run measured RGB/depth/IR/point-cloud/IMU at
  14.52/12.10/13.38/13.24/46.67Hz, with 10.0% raw point-cloud estimated missing.
  Sense/throttle memory was stable near 930/21MiB, swap did not grow, services
  did not restart and Tj peaked at 62.656C.
- The first service-level shadow admission hit an intermittent CLI timeout on
  `/he/visual_odom` and exposed that successful Sense recovery masked the
  original non-zero status. Direct diagnosis then proved one best-effort odom
  publisher at about 8.6Hz and a complete shadow gate passed at 1389MiB cgroup
  memory. Added `restore_sense_on_error` so recovery preserves the failure exit
  status; all 60 HE tests and static checks pass. Final deployment of this
  orchestration fix and a clean wrapper round trip remain pending.
- Reproduced the wrapper-only timeout under one healthy shadow with ROS daemon
  disabled: `ubuntu` received `/he/visual_odom` with status 0 while root timed
  out after 12 seconds with status 124. The publisher remained best-effort at
  about 8.6Hz. Changed only gate execution to `runuser -u ubuntu`; root retains
  systemd ownership and all readiness thresholds remain unchanged.
- Deployed `6a9f01db`; the standard wrapper completed shadow admission in 40
  seconds with status 0. Admission and 30-second independent gates passed at
  1196/1402MiB cgroup memory. The wrapper restored Sense normally; Sense and
  throttle are enabled/active, shadow is static/inactive, all services have zero
  restarts, no RTAB-Map or temporary throttle residue remains, and deployment
  integrity plus the final read-only gate passed.
- Final Orin HTTPS sync failed twice with GnuTLS receive error -110. Preserved
  the fast-forward-only rule by transferring a complete bundle from the pushed
  VM repository and running `git pull --ff-only` against it, then updating the
  local origin tracking ref from the same bundle. Also identified one false
  read-only-gate result caused by a parent SSH command line containing the
  protected `rtabmap` process name; the standalone gate passed. Documented both
  operational hazards and their bounded workarounds.
- Audited the existing Aurora firmware/SDK getter, spatial depth mask, effective
  parameter A/B, USB topology and long-timing evidence for vendor escalation.
  Added a direct English support request with nine concrete vendor questions and
  a whitelist-only package builder. The package excludes sensor images/payloads,
  rosbags, serials and private scene data, and verifies every included derived
  artifact through SHA-256. The VM build produced one request and ten evidence
  files; all internal hashes passed. The extracted package contained no image,
  rosbag, Rerun or database payload and a scan found no home path, IP, password,
  private key or serial value. The final validated package SHA-256 was
  `a1e04fb79c96dd6ff34442fd103cb6231dd05bb8c3989c4f000ed6cd91f933c9`.
- Found that localization health had no direct Aurora depth-quality input and
  could only infer degradation through RTAB-Map outputs. Added a tiny
  `depth_quality` stream computed after the bridge's existing 5Hz NumPy
  conversion: source time plus global, center-40% and bottom-third valid ratios.
  Health now rejects missing, malformed, older-than-1s or below-10% regional
  evidence. The health worker receives no full image and adds no ROS subscriber.
  Four focused and all 64 HE tests, Ruff, blueprint registry and diff checks
  pass. The thresholds are provisional shadow interlocks; Orin evidence remains
  pending and physical calibration/vendor evidence still controls admission.
- Deployed depth-quality health candidate `d8650a7f`. Coordinator logs proved a
  pLCM dictionary connection from HESensorBridge to HELocalizationHealth. In 906
  static samples, global/center/bottom median coverage was
  26.03/19.16/5.64%; every sample added only the bottom coverage reason and the
  maximum metric age was 0.433s. A four-second Aurora outage added
  `depth_quality_stale` after 0.859s and cleared it after recovery; final age was
  0.022s. Shadow peaked near 1408MiB, available memory stayed near 2.78GiB,
  tegrastats swap was flat, services did not restart and all motion gates stayed
  closed. Both runs restored Sense and passed deployment/read-only gates.
- Audited the shadow readiness gate and found it only rejected resource reasons;
  missing, invalid or stale depth-quality evidence could leave admission green.
  Extended its three-second health check to reject those reasons and validate
  every sample's finite 0-1s age and three finite `[0,1]` ratios. Known low
  bottom coverage remains allowed for shadow observation but keeps health
  unhealthy and planner output withheld. Shell, structural, 64 HE unittest,
  focused Ruff, registry and diff checks pass; Orin positive/negative admission
  evidence remains pending.
- Extracted the non-trivial admission rules into
  `validate_shadow_health_report` so production and deterministic tests execute
  the same code. Tests prove fresh complete low-bottom evidence is allowed for
  shadow, while stale/missing depth, high SLAM memory, age above 1s and missing
  ratio fields are rejected. The live gate still captures its own three-second
  report and has no fault override. All 65 HE tests, focused Ruff, shell,
  registry and diff checks pass; final Orin positive admission remains pending.
- Deployed admission hardening through `f1cef694`. The standard wrapper captured
  a live report, passed in 42 seconds and returned status 0; an independent gate
  passed again. Shadow cgroup memory was 1217/1354MiB at the two checks, swap
  stayed at 580MiB and restart counts remained zero. Normal return restored
  Sense and final deployment/read-only gates passed. Combined with the real
  outage stale report and production-function negative tests, missing, invalid,
  stale or incomplete depth evidence can no longer pass shadow admission.
- Added a bounded read-only planner-map withholding diagnostic. It observes
  `/visual_map`, `/localization_health` and `/global_costmap` without retaining
  map payloads or publishing. A shared pure summary fails on missing sources,
  any healthy sample or any planner map. All 66 HE tests, focused Ruff,
  blueprint registry and diff checks pass; 30-second Orin live evidence remains
  pending.

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
- Do not enable tightly coupled VIO from the Madgwick probe. First quantify a
  bounded stationary raw/filtered comparison. Any later use is limited to an
  explicit optional RTAB-Map shadow orientation prior until physical
  camera-to-IMU spatial/time and noise calibration is complete.
- The static comparison failed admission, so do not add Madgwick to the runner
  or set RTAB-Map `wait_imu_to_init=true`. Preserve RGB-D-only shadow until IMU
  bias/noise/axis and physical camera-IMU space/time calibration are available.

## Current State

- The database-boundedness code and runtime configuration are synchronized
  across VM, origin and Orin. Use `git rev-parse HEAD` for final commit identity
  rather than embedding a self-invalidating value here.
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
- Long-duration software timestamp qualification now has a bounded tool but is
  characterized on Orin. It does not pass admission because camera/point-cloud
  gaps remain; hardware synchronization remains unclaimed.
- Serialized point-cloud pre-throttling at 1.2Hz with a 1.3Hz Python guard is
  accepted for the sampled visualization branch after Orin timing, resource and
  service-level shadow qualification. Mode-switch status preservation and
  runtime-user gate execution are deployed and verified in a complete wrapper
  round trip.
- The enhanced diagnostic and effective-parameter A/B are complete. No tested
  setting resolves the stable spatial defect, so the canonical configuration is
  restored and RGB-D navigation admission remains failed. The SDK support-range
  and synchronization fields are now captured but require vendor interpretation.
- The extended static soak exposed active-database growth as a real defect. The
  first threshold-only deployment failed, while the corrected unlinked-node
  persistence setting passed a full 600-second Orin soak with about 99.0%
  lower database growth. The 256MiB hard watchdog remains enabled.
- Native child cleanup, lifecycle order, host RPC-client cleanup and non-parent
  worker waits are fixed and verified on Orin. Normal stop completes inside the
  CLI SIGTERM grace with one shutdown round, no error and no residue.
- The map-load contract and static same-scene read-only reload are verified on
  Orin. Moving/displaced-start relocalization and loop closure remain open.
- Real health-transition instrumentation, total Aurora outage/recovery and
  current bad-but-fresh partial depth coverage are verified on Orin. Dynamic
  scene and moving tracking failures remain open.
- Raw IMU orientation is unusable as published. Madgwick is runnable but failed
  the static admission gate. A 598-second raw run also proved a stable but large
  x gyro offset, so the shadow chain remains RGB-D-only.
- Static bad-but-fresh RGB/depth transitions and recovery are proven on Orin.
  Static CameraInfo-only synchronization loss is also proven. Moving tracking
  loss and dynamic scenes remain open.
- Structural malformed/missing CameraInfo and runtime drift beyond the approved
  intrinsic tolerance are proven. Physical target calibration and physical
  camera-to-base/camera-to-IMU extrinsics remain open.
- The HE Sense memory A/B is complete and supports retaining 128MB. The running
  Orin service is active at the candidate commit with zero restarts and about
  870MiB steady cgroup memory. Teleop, visual-SLAM, worker policy and all
  control modules remain unchanged; moving and physical-calibration gates are
  still open.
- Shadow resource-health hardening is deployed and statically qualified. The
  optimized six-worker/128MB dual-path shadow is now deployed and passed static
  function/resource soak. Static systemd isolation, cgroup containment and
  bounded mode switching are also Orin-qualified. Physical calibration,
  multi-hour/moving resource behavior and every moving qualification gate
  remain open.
- Planner-map withholding has a VM-qualified bounded diagnostic candidate, but
  is not yet live-qualified on Orin. Keep `/global_costmap` absent and navigation
  disabled until its real shadow capture is preserved as evidence.

## Resume Instructions

1. Read this log, ADR-001 and the final shadow soak evidence.
- Preserve the CameraInfo evidence boundary: missing, structurally invalid and
  runtime values beyond the approved intrinsic tolerance are covered. The
  approved baseline itself still requires physical calibration-target proof.
- Read the fresh-content fault evidence before changing health thresholds; do
  not treat blank-depth freshness fallback as explicit tracking-loss status.
- Read the static IMU evidence before changing RTAB-Map inputs. Do not run an
  IMU-prior A/B until bias/noise/axis and camera-IMU calibration are available.
2. Run a static matte-target and camera pitch/height experiment to separate
   floor reflectivity/grazing-angle effects from sensor defects.
3. Evaluate a controlled move from the shared USB 2.0 hub to the available
   10Gbps root port if physical access is approved.
4. Escalate firmware 2.0.8/SDK 1.1.22 evidence to the vendor if target coverage
   remains abnormal, requesting optical specifications and the documented
   `SupportedInfo.depth_range` interpretation.
5. Use the new nominal-extrinsics audit to plan physical camera-to-base and
   camera-to-IMU calibration; do not promote the nominal values to calibrated.
6. Keep public benchmark tables source-scoped and update them only when a new
   candidate has code, license, runtime and deployability evidence.
7. After a new vehicle-down confirmation, record moving, loop-closure and
   relocalization datasets and decide whether RTAB-Map can graduate beyond the
   shadow baseline.
8. Preserve the verified normal shadow shutdown path; do not replace it with
   `--force` in deployment procedures.
9. Do not enable motion or restore LD19.
10. Preserve the qualified static shadow unit and bounded switch; do not enable
    shadow at boot or weaken its complete readiness gates.

## Open Questions

- Can Aurora depth coverage and synchronization meet RGB-D/VIO prerequisites?
- Can RTAB-Map produce navigation-usable map coverage after the camera can move?
- Will the full DimOS shadow stack preserve the measured memory margin in
  multi-hour operation and moving-map workloads?
- Can the public candidate results be normalized enough to support a stronger
  SOTA comparison without mixing datasets, inputs and alignment methods?
