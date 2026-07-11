# Aurora Sensor Rate Reference

## Metadata

- Date: 2026-07-11 12:53 CST
- Session id: current Codex desktop thread
- Project: dimos-wd-m20
- Workspace: VM `/home/markus/work/dimos_wd_m20`
- Task: document Aurora raw and bounded bridge rates for future algorithm and optimization work
- Status: completed
- Branch if relevant: `codex/he-orin`

## User Request Summary

Record the distinction between Aurora hardware/ROS frame rates and current
HESensorBridge/Rerun rates so future algorithm and optimization work can verify
the intended behavior.

## Work Done

- Added `dimos/robot/he/docs/aurora-sensor-rate-reference.md` with raw topic
  formats, measured rates, bridge defaults, observed DimOS rates and resource
  evidence.
- Documented that RGB/depth/IR are about 15Hz and point cloud about 13-15Hz at
  ROS, while the viewer-facing outputs are intentionally 5Hz and 1Hz.
- Documented the future full-rate local SLAM/perception path separately from
  the bounded latest-only Rerun path.
- Added recheck commands and highlighted depth validity, synchronization,
  alignment, extrinsics and memory as mandatory gates.
- Linked the reference from the HE README and version-controlled deployment plan.

## Decisions

- Keep current runtime configuration unchanged; this task only records verified
  behavior and future architecture guidance.
- Do not describe the bounded viewer rate as an Aurora hardware limit.

## Current State

- Documentation complete; no runtime or control behavior changed.
- Real motion remains disabled and visual SLAM remains deferred.

## Resume Instructions

Read `dimos/robot/he/docs/aurora-sensor-rate-reference.md` before changing
camera rates, adding SLAM, or optimizing the sensor/Rerun process.

## Open Questions

- Aurora depth coverage and multi-stream synchronization remain unverified for SLAM.
