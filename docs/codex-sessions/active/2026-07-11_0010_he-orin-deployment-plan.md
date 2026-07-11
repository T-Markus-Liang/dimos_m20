# HE Orin Deployment Plan

## Metadata

- Date: 2026-07-11 11:28 CST
- Session id: current Codex desktop thread
- Project: dimos-wd-m20
- Workspace: WD M20 baseline on VM plus HE deployment target `ubuntu@192.168.1.106`
- Task: finish the lightweight WD DimOS/HE deployment, characterize the lifted chassis and executable command boundaries, and document deferred physical feedback/visual SLAM
- Status: active - lifted command and software-limit characterization complete; physical feedback remains deferred
- Branch if relevant: `codex/he-orin` from `feat/wd/m20`

## User Request Summary

Update the Orin NX DimOS lightweight deployment plan for the actual HE
Ackermann robot, then later back up relevant existing-system files, free disk
space, deploy WD DimOS, and use the existing chassis, Aurora 930 depth camera
and LD19 lidar.

## Work Done

- Completed the hardware audit in the preceding session log.
- Replaced the macOS deployment document with an HE-specific plan:
  `/Users/markus/Downloads/orin nx-dimos轻量化部署方案.md`.
- Documented real hardware interfaces, data rates, resource budget, HE module
  names, required safety semantics, P0 blockers and gated deployment sequence.
- Backed up 17GB of hardware workspaces, selected old AI assets, configuration,
  and software manifests to
  /Users/markus/Backups/HE-OrinNX-2026-07-11 on macOS.
- Verified the ROS workspace, Aurora workspace, systemd units, udev rules,
  TensorRT exports, and Ollama directory with rsync dry runs.
- Removed the backed-up models, TensorRT exports, Ollama data, old VLA sources,
  Node environment, downloads, and user caches. Cleared 3.5GB of unused CUDA
  pip binaries while retaining the active pyserial dependency.
- Increased Orin root free space from about 4.4GB to 26GB.
- Verified that Aurora, chassis control, odometry, and joystick services remain
  active and that the ROS graph and /dev/rrc and /dev/lidar mappings remain
  available.
- Installed the WD repository at `/home/ubuntu/he/dimos_wd_m20` on Orin using
  a Git bundle transferred through macOS because the configured proxy was stale.
- Installed the minimum Python runtime in `/home/ubuntu/he/dimos_wd_m20/.venv`;
  added `python3.10-venv`, ran `ensurepip`, installed the editable core package,
  and added the missing runtime dependency `matplotlib` for Rerun.
- Added the HE package on the VM baseline and synced it to Orin:
  `HESensorBridge`, `HEConnection`, `he-sense-headless`, and
  `he-teleop-headless`. The control bridge defaults to disabled and clamps its
  future enabled output to 0.10m/s and 0.30rad/s with a 200ms watchdog.
- Fixed two WD API compatibility issues in the HE adapter: blueprint atoms must
  be combined with `autoconnect`, and `Module` subclasses must pass keyword
  configuration through `__init__(self, **config_args)`.
- Verified `dimos list`, Python imports, syntax compilation, the sensor-only
  blueprint, and the disabled teleoperation blueprint on Orin. The latter
  deployed all modules while `/cmd_vel` had zero publishers.
- Repaired the ROS hardware baseline: disabled the duplicate
  `ros-robot-controller.service`, removed the Wi-Fi button service's serial
  board/buzzer access, and restarted `odom-publisher.service`. `/dev/rrc` now
  has one owner and the IMU stream recovered at about 47Hz.
- Restored the missing LD19 driver from the official source into the isolated
  `/home/ubuntu/he/ldlidar_ws`, built only that ROS package, and enabled
  `he-ld19.service`. `/scan` is a single `lidar_frame` publisher at 10Hz.
- Published the existing platform camera transform through
  `he-camera-tf.service`; both camera and lidar are connected to
  `base_footprint` in the TF graph.
- Enabled `he-dimos-sense.service`, which runs only `he-sense-headless`.
  It ran for over two minutes with no restarts and about 560-610MB cgroup
  memory. A six-second LCM sample received IMU 95, odom 97, and lidar 36
  messages. `/cmd_vel` still has zero publishers.
- Added the three reproducible systemd units to
  `dimos/robot/he/deployment/` in the VM baseline and updated the deployment
  plan with current service state, resource evidence, and all fixes.
- Evaluated RF2O laser odometry in an isolated Orin workspace. It builds and
  emits `/odom_rf2o` at about 10Hz after ROS package, QoS, and initial
  quaternion fixes, but static tests still show centimeter-scale drift and yaw
  noise. It remains a candidate only and is not a service or navigation input.
- Saved the exact RF2O compatibility changes as
  `dimos/robot/he/deployment/rf2o-he-candidate.patch` and verified that the
  patch reverses cleanly against the current Orin test source.
- Added six standard-library unit tests for `HEConnection`: disabled default,
  command limits, lateral removal, non-finite rejection, 200ms stale-command
  stop, and repeated shutdown zero output. All six pass on Orin.
- Re-audited the live platform: all five required services are active with no
  restarts, each serial device has one owner, `/cmd_vel` has zero publishers,
  and no RF2O test process or `/odom_rf2o` publisher remains.
- Measured the live ROS rates again: LD19 about 10Hz, IMU about 47Hz, and
  open-loop odom about 47-48Hz. Current resources are about 23GB disk free,
  3.9GiB available RAM, 588MiB swap used, and 13-36% per-core CPU in the sample.
- Enabled the existing Rerun `latest_only_entities` behavior for HE lidar,
  odom, IMU, and optional camera point cloud while retaining the 256MB server
  recording window. Restarted only the read-only sensor service; `/cmd_vel`
  remained at zero publishers.
- Added systemd cgroup protection to `he-dimos-sense.service` with
  `MemoryHigh=1G` and `MemoryMax=1280M`. The limits are active on Orin.
- Added and ran `dimos/robot/he/deployment/verify-he-readonly.sh`. It passed all
  service, serial-owner, topic-owner, port, memory, and live-sample checks and
  explicitly reported that the motion gate remains closed.
- Confirmed `/aurora/points2` has zero subscribers. With no remote viewer, a
  10-second Wi-Fi sample was only about 0.008Mbps RX and 0.013Mbps TX.
- Verified `all_blueprints.py` byte-for-byte against the repository generator;
  corrected only the generated alphabetical ordering of the two HE modules.
- Completed a post-restart five-minute bounded soak. The sensor cgroup rose
  from about 556MiB to 603MiB and the final read-only gate measured 609MiB,
  with `NRestarts=0`, 3.9GiB system memory available, and the 1.25GiB hard cap
  active. This is bounded and healthy but not yet proof of a natural plateau.
- Added and executed `verify-he-control-dry-run.py` against the isolated ROS
  topic `/he_safety_test/cmd_vel`. The actual ROS message was clamped to
  0.10m/s and -0.30rad/s with lateral velocity removed; after 250ms without a
  refresh the observed command was zero, and the shutdown command was zero.
- Verified the real `/cmd_vel` had zero publishers both before and after the
  isolated control dry run. The test topic and process disappeared on exit.
- Completed the final remote completion audit. The read-only gate passed again:
  all five required services were active with zero restarts, the duplicate
  controller was disabled/inactive, each serial device had one owner, real
  `/cmd_vel` had zero publishers, Aurora raw point cloud had zero subscribers,
  and only port 9877 was listening among the HE viewer ports.
- Recorded the final remote resource snapshot: about 689MiB for the bounded
  sensor service, 3.8-3.9GiB system memory available, and 23GB disk free.
- On the first post-block resume audit, no new field evidence was supplied.
  The read-only service remained active with zero restarts at about 719MiB,
  real `/cmd_vel` still had zero publishers, and no RF2O or isolated-control
  test process remained. The physical blocker is unchanged.
- On the second post-block resume audit, the service remained active with zero
  restarts at about 729MiB; growth had slowed and remained below MemoryHigh.
  Real `/cmd_vel` still had zero publishers and Aurora raw point cloud still
  had zero subscribers. No new field evidence was supplied.
- On the third post-block resume audit, the service remained active with zero
  restarts at about 741MiB, below MemoryHigh, and real `/cmd_vel` still had
  zero publishers. No test process or new field evidence appeared. The resumed
  goal is blocked again under the three-consecutive-turn rule.
- User confirmed the vehicle was lifted and site safety measures were ready.
  Resumed the goal and executed real low-speed HEConnection pulses.
- Changed HEConnection shutdown to publish three zero commands at the configured
  20Hz interval; all six unit tests pass.
- Fixed the existing Ackermann reset-servo bug so zero velocity centers steering
  at PWM 1500 in addition to stopping all four motors.
- Passed lifted forward, reverse, left, and right tests at 0.03m/s. Downstream
  motor commands matched each case, watchdog stop was about 208ms, five final
  motor samples were zero, and three final steering samples were centered.
- Installed and integrated ROS twist_mux with manual priority 100 and navigation
  priority 10. Both input timeouts are 100ms; the final odom watchdog is 100ms.
- Remapped all legacy odom command subscriptions so only `/he/final_cmd_vel`
  reaches the Ackermann controller. HEConnection now defaults to
  `/he/nav_cmd_vel`; the old raw `/cmd_vel` path is absent.
- Fixed joystick behavior so `disable_servo_control=True` removes its direct PWM
  publisher and held nonzero axes refresh manual commands. PWM ownership is now
  one publisher: odom_publisher.
- Verified synthetic manual priority, raw Joy disconnect, final speed limits,
  mux SIGKILL stop, and odom service stop. Measured motor-zero delays were 66ms,
  116ms, and 60ms respectively, all below 200ms.
- Added reproducible controller, joystick, twist_mux, systemd, and lifted-gate
  artifacts under `dimos/robot/he/deployment/`; generated patches were applied
  to reconstructed baselines and byte-compared with the live sources.
- Encountered and documented the old setuptools/config I/O error and the
  PYTHONNOUSERSITE colcon-ros hook loss. Restored controller package.dsv so the
  package and service remain operational.
- Re-ran the complete lifted gate after the operator reconfirmed the vehicle
  was safely raised. Forward, reverse and left passed on the first controlled
  run; the first right probe missed DDS samples and failed closed, then passed
  after endpoint stabilization. Every successful case ended with five zero
  motor frames and three centered steering frames. The final graph has zero
  `/he/nav_cmd_vel` publishers, and all four runtime services are active with
  zero restarts.
- Verified the VM and Orin `dimos/robot/he` trees have the same aggregate
  SHA-256 (`2f66e293...d37dc`), removed generated HE `__pycache__` directories,
  and passed the final read-only gate at 892MiB sensor-service memory with
  3.6GiB system memory available and 23GB disk free.
- Found that the working Orin virtual environment does not contain
  `.venv/bin/activate`. The environment itself and systemd service are healthy;
  use `.venv/bin/python`/`.venv/bin/dimos` directly, or set `VIRTUAL_ENV` and
  prepend `.venv/bin` to `PATH`. Do not rebuild it merely to restore activation.
- Added `verify-he-sensors.py`, a read-only live quality gate that does not
  subscribe to the Aurora point cloud or publish motion. It passed with LD19 at
  10.00Hz, 508 bins, 91.1% valid ranges and 0.02-25m configured range; IMU,
  command-integrated odom and RGB CameraInfo frames/timestamps also passed.
- Confirmed the static TF tree connects base, lidar and camera frames, but no
  dynamic `odom -> base_footprint` transform exists because the legacy odom
  publisher's TransformBroadcaster is commented out. `/odom_raw` remains an
  untrusted command-integrated message only.
- Audited Aurora depth and localization capability. `slam_mode=0` selects dual
  ToF data, not SLAM; the driver publishes no pose/odometry. A static 640x400
  depth snapshot had about 18.6% nonzero pixels and an empty central ROI, so it
  is not ready to support RGB-D odometry without camera/configuration work.
- Re-audited RF2O and Slam Toolbox. Slam Toolbox cannot use the absent dynamic
  odom TF directly. One RF2O diagnostic waited for `/base_pose_ground_truth`
  because `init_pose_from_topic` was not overridden to empty; it provides no
  new accuracy evidence. All temporary localization processes/topics were
  removed afterward.
- Updated the deployment document to end the current stage at static/lifted
  deployment verification. The user selected visual SLAM as the next mapping
  and localization direction; DINOv3 is documented only as an optional learned
  feature/place-recognition component, not a standalone geometric SLAM system.
- Completed the static closeout regression without installing development
  extras: both HE blueprints were discoverable, Python compilation passed, all
  six `unittest` safety tests passed, the isolated ROS control dry-run passed,
  the live sensor quality gate passed, and the read-only runtime gate passed.
- Verified seven required services are active/enabled with zero restarts,
  systemd unit verification passes, recent service journals contain no
  warnings/errors, port 9877 is the only HE viewer port, and all temporary
  localization/probe processes and topics are absent.
- Recorded the final resource snapshot: sensor cgroup about 892MiB with 1GiB
  MemoryHigh and 1.25GiB MemoryMax, 3.6GiB system memory available, 531MiB swap
  used and 23GB disk free. VM and Orin HE trees match aggregate SHA-256
  `6b0e38d...687b6`.
- Expanded `/Users/markus/Downloads/orin nx-dimos轻量化部署方案.md` with the
  complete current-stage closeout, troubleshooting table, and a separate
  visual-SLAM/DimOS exploration roadmap.
- Strengthened `verify-he-readonly.sh` for the final command architecture. It
  now checks all seven services active/enabled with zero restarts, joystick to
  mux to odom/PWM endpoint ownership, absence of the legacy `/cmd_vel`, bounded
  memory settings, expected ports, and absence of GUI, SLAM, navigation and
  isolated-test processes/topics.
- Added `verify-he-static-deployment.sh` as the single static closeout command.
  It runs pre/post read-only gates, blueprint discovery, six standard-library
  tests, isolated control dry-run and live sensor quality checks. It never calls
  the lifted real-command verifier.
- Fixed a closeout-run race caused by DDS endpoint discovery cleanup. The
  orchestration waits up to 10 seconds for isolated endpoints while preserving
  the strict final gate; no fixed long delay or weakened check was introduced.
- Ran the final one-command closeout through actual process completion. It
  printed `HE static deployment closeout: PASS`, `Real motion: DISABLED`,
  `Visual SLAM/navigation/exploration: DEFERRED`, and
  `STATIC_CLOSEOUT_RC=0`. The final nav publisher count remained zero.
- Recomputed and matched the VM/Orin HE aggregate SHA-256 as
  `d424190c...14d2a0` after the verifier additions.
- Audited repository-to-live deployment integrity: all four HE systemd units
  and the odom drop-in match `/etc` byte-for-byte; all three ROS safety patches
  reverse-check as applied; controller/joystick build copies match source; and
  the odom launch install symlink resolves to the patched source.
- Added `verify-he-deployment-integrity.sh` and included it in the canonical
  static closeout. The final integrated run passed with
  `STATIC_CLOSEOUT_RC=0`, and the new VM/Orin aggregate SHA-256 matches as
  `062e0e2b...25cd7`.
- Completed the third consecutive post-closeout audit. The read-only and
  deployment-integrity gates still pass at about 892MiB sensor memory, 3.6GiB
  available RAM and 23GB disk free; navigation remains at zero publishers.
  Remaining work requires lowering/moving the vehicle and a user-approved
  visual-SLAM field phase, so the overall session is now explicitly blocked.
- Rechecked the live platform for the operator status question. All seven
  required services remain active/enabled with zero restarts; deployment
  integrity and read-only gates pass; `he-sense-headless` and the disabled
  `he-teleop-headless` are discoverable; `/he/nav_cmd_vel` still has zero
  publishers. Current resources remain 23GB disk free, 3.6GiB available RAM
  and about 892MiB for the sensor cgroup.
- Clarified the acceptance boundary: current static/runtime dependencies are
  complete, while visual-SLAM/navigation extras are deliberately absent. The
  command safety chain has lifted/downstream evidence, but `/odom_raw` is
  command-integrated and cannot prove a closed feedback-control loop.
- Audited the live final-command path before characterization and found that
  `/he/final_cmd_vel` entered `cmd_vel_callback`, bypassing limits implemented
  only in `app_cmd_vel_callback`. Moved finite-value validation and 0.10/0.30
  clamping into the common final callback, updated the reproducible patch, and
  synchronized ROS source/build copies.
- Added guarded `characterize-he-chassis.py` and ran 83 lifted real-chain
  trials over 0.001-0.15m/s and +/-0.02 to +/-0.50rad/s. Explicit motor stop
  median was 2.959ms; timeout stop was 112.772-150.913ms with 129.586ms median;
  command-layer RPS/PWM/odom errors were zero.
- Confirmed `twist_mux` goes silent rather than publishing zero on timeout; the
  independent odom watchdog performs motor zero and steering recenter. Updated
  the probe to record this behavior without weakening downstream stop checks.
- Added `dimos/robot/he/README.md` and
  `dimos/robot/he/docs/chassis-characterization-2026-07-11.md`. The report
  explicitly separates ROS actuator-command precision from unavailable
  physical wheel-speed and steering-angle feedback.
- Re-ran the complete static closeout after testing. It passed with navigation
  disabled and no characterization process remaining. VM HE aggregate SHA-256
  is `66cfb52c...fb1e5`.
- Extended `characterize-he-chassis.py` with a dependency-free `--suite limits`
  mode and corrected its prediction model for the Ackermann `1e-8rad/s`
  steering threshold. The original characterization suite remains the default.
- Ran 74 additional lifted boundary trials covering positive/negative speed
  deadband and clamp, left/right steering PWM quantization, 34-degree
  saturation, angular clamp, and steering commands at zero linear speed. All
  downstream RPS/PWM/open-loop odom errors were zero.
- Confirmed the software motor-command threshold is `+/-1e-8m/s` and the final
  speed range is `[-0.10,+0.10]m/s`. This is not the physical wheel-motion
  deadband because no wheel encoder or external motion measurement exists.
- Confirmed an asymmetric first steering PWM count caused by `int()` truncation:
  left changes at `+1e-8rad/s`, while right first changes between -0.00044 and
  -0.00045rad/s at 0.05m/s. Front PWM saturates at 1122/1877 near
  0.19047456rad/s, before the final yaw-rate limit of `+/-0.30rad/s`.
- Stored the limit evidence at
  `logs/he-chassis-command-limits-20260711.json`, SHA-256
  `7a96c21f...dc5fe`, and updated the HE report and macOS deployment plan with
  the exact software/PWM versus physical-measurement boundary.
- Re-ran the canonical static closeout after the limit suite and documentation
  sync. Deployment integrity, six HEConnection tests, isolated ROS dry-run,
  sensor quality and both read-only gates passed; real motion remained disabled
  and `/he/nav_cmd_vel` returned to zero publishers.
- Verified VM and Orin `dimos/robot/he` trees match aggregate SHA-256
  `84e2f2cc...429cb`; both copies of the new limit JSON match its recorded hash.
- Audited the HE work against `origin/feat/wd/m20`. Only two existing DimOS
  files differ: `all_blueprints.py` registers the two HE blueprints/modules,
  and `m20_dan_nav.py` replaces the undefined `_m20_dan_rerun` reference with
  the branch-compatible `vis_module(...)` construction. The HE implementation
  itself is isolated under the 24-file `dimos/robot/he/` package.
- Confirmed the HE architecture remains layered: `HESensorBridge` converts and
  rate-limits ROS sensors; headless blueprints provide bounded Rerun output;
  `HEConnection` is a disabled-by-default bounded DimOS command adapter; ROS
  `twist_mux` arbitrates joystick over navigation; the patched final controller
  owns Ackermann kinematics, final limits, timeout stop and steering recenter.
- Reconfirmed that no `he-nav-headless` exists. RF2O remains only a documented
  candidate patch and is not installed as a navigation/localization service.

## Decisions

- Use `feat/wd/m20` as the DimOS development baseline; do not reuse the M20
  robot package as a false hardware abstraction.
- Create a separate HE adapter surface: `HESensorBridge`, `HEConnection`,
  `HEAckermannSafety` and HE-specific headless blueprints.
- Reuse the existing ROS Ackermann layer via `/cmd_vel` initially instead of
  publishing motor or PWM messages directly.
- Do not begin real motion until ROS controller ownership, TF connectivity and
  command-stop behavior are resolved.
- Preserve the current ROS and hardware driver workspaces until their HE
  replacement passes the teleoperation safety gate.
- Do not continue lidar-only mapping or mobile localization while the vehicle
  is raised. Complete and document the current static deployment first.
- Treat visual SLAM and DimOS autonomous exploration as a separate next phase:
  collect synchronized field data, benchmark offline, run on-device shadow
  mode, then integrate map/exploration with control disconnected.

## Current State

- WD DimOS is installed and its staged HE adapters are present on both the VM
  baseline and Orin. Orin currently has about 23GB free; the virtual environment
  is about 2GB and no heavy extras or simulation packages were installed.
- `he-dimos-sense.service` is enabled and supplies Rerun gRPC on port 9877
  plus the bounded HE LCM sensor streams. `he-teleop-headless` remains a
  disabled-control validation blueprint; real commands have only been sent by
  the guarded, short-lived lifted-gate verifier.
- Start commands must use `bash -lc` to source `/opt/ros/humble/setup.bash`.
  The Orin default zsh shell misinterprets the Bash-specific ROS setup script.
- Serial ownership, LD19 `/scan`, nominal camera static TF and repeatable live
  sensor checks are resolved. Camera measured extrinsics, depth validity,
  trusted visual localization and physical sensor directions remain deferred
  until the vehicle can move; they block map/navigation and automatic exploration.
- The Rerun recording window remains configured at 256MB, HE live entities use
  latest-state display semantics, and Aurora raw point cloud remains disabled.
  The full sensor service now has 1GiB memory pressure and a 1.25GiB hard cap;
  the final post-restart read-only gate measured about 609MiB with 3.9GiB
  available system memory. Longer plateau observation remains useful but
  cannot exceed the cgroup hard limit unchecked.
- HEConnection now has both unit-level safety evidence and an actual ROS
  transport dry run on an isolated topic. This does not satisfy the physical
  motion gate; `enabled=False` remains unchanged in every runnable HE blueprint.
- The lifted software/downstream control tests pass, but operator visual
  confirmation of wheel and steering directions is still pending. HEConnection
  remains disabled after every test and `/he/nav_cmd_vel` has zero publishers.
- Navigation remains deliberately out of the current static deployment scope.
  No `he-nav-headless`, visual-SLAM service or autonomous-exploration output has
  been added.
- The current static deployment stage is reproducibly complete. The active
  session remains open only because mobile visual-SLAM, mapping and autonomous
  exploration are a later phase of the overall HE objective.
- No further static code or dependency installation is justified while blocked;
  doing so would add risk without producing the missing physical localization
  evidence.
- The current control chain has no acceleration/jerk ramp and no measured wheel
  speed or steering angle. Physical deadband, settling, backlash and ground
  accuracy remain future measured-feedback work.
- Focused command-limit testing is complete. The executable software ranges are
  speed `[-0.10,+0.10]m/s`, yaw rate `[-0.30,+0.30]rad/s`, and steering PWM
  1122-1877; physical minimum/maximum motion remains unknown without feedback.
- The goal remains blocked only at its mobile visual-SLAM/navigation phase.
  Static HE deployment, sensor bridging and lifted command safety can be used as
  the stable baseline; trusted localization and `he-nav-headless` still require
  camera/depth work plus vehicle-down field data and a new safety authorization.
- The canonical static regression command is
  `bash dimos/robot/he/deployment/verify-he-static-deployment.sh` from the Orin
  repository root. A pass does not authorize real motion.
- The closeout now also proves live deployment files and loaded ROS Python
  build copies correspond to repository artifacts, preventing source/install
  drift from being mistaken for a reproducible deployment.
- Three old-data locations contained unreadable files: an AI safetensors
  weight, temporary ASR files, and parts of old Downloads and Node assets.
  Their readable contents were copied; the residual unreadable Downloads
  directory requires an offline filesystem repair if removal is needed.

## Resume Instructions

1. Record operator confirmation that forward/reverse wheel motion, left/right
   steering, recentering, and service-stop behavior matched the test labels.
2. Use the completed deployment report as the baseline; do not reinstall or
   alter the static HE runtime while planning the next phase.
3. In the next phase, fix/characterize Aurora depth, measure camera/IMU
   extrinsics and collect synchronized field data before selecting a visual
   SLAM engine. Retain `/odom_raw` as display-only open-loop odometry.
4. Keep HEConnection disabled while lowering the vehicle. If operator visual
   checks pass, mark the lifted control gate complete but do not enable navigation.
5. Run the selected visual SLAM in shadow mode, then integrate DimOS mapping and
   exploration with command output disconnected. Add `he-nav-headless` only
   after localization and all physical safety evidence exist.

## Open Questions

- Which visual SLAM geometry frontend will pass the offline HE dataset and Orin
  resource benchmark: RGB-D, visual-inertial, or another measured approach?
- Did the operator visually observe the expected forward/reverse wheel direction,
  left/right steering direction, recentering, and immediate stop on service exit?
