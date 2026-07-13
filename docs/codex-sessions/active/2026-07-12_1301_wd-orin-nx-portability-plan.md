# WD Orin NX Portability Planning

## Metadata

- Date: 2026-07-12 13:01 CST
- Session id: current Codex desktop thread
- Project: dimos-orin-nx
- Workspace: VM `/home/markus/work/dimos_wd_m20`
- Task: create `wd/orin_nx` from WD M20 and plan portable integration of validated HE lightweight deployment work
- Status: active - Phase 1 complete; Phase 2/3 common adapters implemented
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
- Phase 2/3 common profile, sensor and command adapters are implemented and
  focused tests pass; they are ready for their stage commit and push.
- Generic sense composition, live ROS integration, read-only graph validation,
  portable Orin systemd/storage runtime and installer remain.

## Resume Instructions

Read `docs/orin-nx/portability-plan.md`, verify the Phase 2/3 stage commit is
on origin, then implement Phase 4 portable Orin runtime. Start with storage
health extraction and environment-file-based systemd templates; keep motion
services disabled and validate installer dry-run behavior.

## Open Questions

- Whether the first second-platform target uses ROS Twist or a direct chassis
  protocol.
- Which live ROS fixture should be used for the first VM bridge integration
  test.
