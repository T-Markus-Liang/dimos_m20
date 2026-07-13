# WD Orin NX Portability Planning

## Metadata

- Date: 2026-07-12 13:01 CST
- Session id: current Codex desktop thread
- Project: dimos-orin-nx
- Workspace: VM `/home/markus/work/dimos_wd_m20`
- Task: create `wd/orin_nx` from WD M20 and plan portable integration of validated HE lightweight deployment work
- Status: active - Phase 1-3 core pushed; Phase 4 runtime core implemented
- Branch if relevant: `wd/orin_nx` from `feat/wd/m20` at `98713d97`

## User Request Summary

Create a new Orin NX branch from WD M20, then plan how to integrate completed
and validated HE lightweight deployment work while turning sensors and chassis
communication into reusable templates for other Orin NX robot platforms.

## Work Done

- Verified the VM worktree was clean.
- Fetched upstream `feat/wd/m20` and confirmed local/upstream identity at
  `98713d97341bc9392e5dd531b1c13aaf98782a23`.
- Created `wd/orin_nx` from that commit, pushed it to
  `T-Markus-Liang/dimos_m20` and configured upstream tracking.
- Audited file, line and commit differences through HE head `f1b68218`.
- Separated generic lifecycle/resource/safety work from HE/Aurora/Ackermann
  platform code and large evidence.
- Inspected HE sensor, command, visual SLAM, systemd and verification hardcoding.
- Defined a three-layer architecture: Orin common runtime, strict platform
  profile and robot-specific adapter.
- Produced the phased migration, source matrix, validation gates, risks and
  completion criteria in `docs/orin-nx/portability-plan.md`.
- Verified the planning branch still contains no runtime/code changes and that
  documentation formatting and branch provenance are clean.
- On 2026-07-13, corrected the architecture boundary after user review: Orin NX
  is a compute target, reusable ROS adapters belong under `dimos/hardware`, and
  HE remains a robot profile/composition rather than the common package.
- Completed Phase 1 by porting the final HE core lifecycle fixes without HE
  files: idempotent coordinator shutdown, fork-safe worker waits, zombie PID
  detection, daemon shutdown ordering and asynchronous stop-RPC cleanup.
- Improved stop-RPC settling to use one coordinator-wide 100ms budget instead
  of per-module waits. All 49 focused lifecycle/coordinator tests and Ruff pass.
- Added a strict JSON `PlatformProfile` with validation for enabled sensor
  topics/rates, duplicate topics, motion backend and lateral limits, and
  runtime memory ordering.
- Added a reusable `ROS2SensorBridge` for standard Image, CameraInfo,
  PointCloud2, Imu and Odometry messages. Channels are independently bounded
  and disabled by default; an all-disabled module does not create a ROS node.
- Added a reusable fail-closed `ROS2TwistConnection` with finite checks,
  independent limits, optional lateral motion, stale-command zeroing and three
  zero commands during shutdown. Motion output remains disabled by default.
- Added the HE reference profile under `dimos/robot/he/profile.json` with the
  previously measured Aurora, odometry, IMU, point-cloud and resource values.
- Verified the HE profile constructs both generic module configs and confirmed
  common files contain no HE, Aurora or fixed user-home paths.
- Verification: 19 focused profile/sensor/command tests pass, Ruff passes and
  `git diff --check` passes. The remaining pytest warning is the repository's
  pre-existing custom asyncio fixture deprecation warning.
- Committed and pushed the common profile and ROS adapter stage as
  `89099ccf feat(hardware): add portable ROS platform adapters`.
- Extracted the HE-proven NVMe SMART and current-boot kernel error policy into
  the generic Orin compute layer. The CLI writes a bounded JSON report and
  exits nonzero for warning, media, spare or kernel failures.
- Added deterministic systemd template rendering from the robot profile,
  including runtime user, repo, Python/CLI paths and memory budgets. The
  installer supports dry-run and offline roots and never enables or starts a
  service.
- Added storage-before-runtime ordering, ROS environment loading and separate
  sense/shadow units. Both units validate the profile before startup and reject
  motion-enabled profiles by default.
- Verification: 11 focused storage/installer/profile-gate tests pass, shell
  syntax passes, HE profile is accepted as motion-disabled, and rendered units
  pass `systemd-analyze verify`. VM-wide netplan permission and snapd key
  warnings are unrelated to the rendered units.

## Decisions

- Base the branch on upstream WD M20, not HE.
- Do not cherry-pick the complete HE history.
- Keep motion disabled and visual SLAM optional.
- Treat HE as the first reference profile, not as the common implementation or
  parent class.
- Use standard ROS messages for common adapters and leave direct hardware
  protocols in robot packages.
- Keep transport selection orthogonal to hardware adapters; LCM and Zenoh are
  DimOS runtime backends, not sensor-driver contracts.

## Current State

- Branch exists locally and on origin.
- Phase 1 is committed and pushed.
- Phase 2/3 common profile, sensor and command adapters are pushed.
- Phase 4 storage admission, service templates, installer and profile motion
  gate are implemented and ready for their stage commit and push.
- Generic sense composition, live ROS integration, graph-level publisher
  validation, resource soak collection and visual shadow extraction remain.

## Resume Instructions

Read `docs/orin-nx/portability-plan.md`, verify the Phase 4 stage commit is on
origin, then add generic sense composition and live fake-ROS integration before
starting optional visual shadow extraction. Keep all motion services absent.

## Open Questions

- Whether the first second-platform target uses ROS Twist or a direct chassis
  protocol.
- Which live ROS fixture should be used for the first VM bridge integration
  test.
