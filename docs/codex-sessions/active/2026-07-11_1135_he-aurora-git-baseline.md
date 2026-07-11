# HE Aurora Git Baseline

## Metadata

- Date: 2026-07-11 11:35 CST
- Session id: current Codex desktop thread
- Project: dimos-wd-m20
- Workspace: VM `/home/markus/work/dimos_wd_m20`; runtime target `/home/ubuntu/he/dimos_wd_m20`
- Task: establish pushed Git version control, retire LD19 from HE, and make all Aurora sensor outputs default HESensorBridge inputs
- Status: active - baseline audit complete; implementation pending
- Branch if relevant: `codex/he-orin` from `origin/feat/wd/m20`

## User Request Summary

Use Git commits and pushes for all subsequent HE changes with complete commit
messages. Retire the single-line LD19 from the HE platform and make every
Aurora output available through `HESensorBridge` by default.

## Work Done

- Confirmed the VM workspace is already a Git clone of
  `https://github.com/MeloLong/dimos.git` on `codex/he-orin`, but the branch has
  no upstream tracking and the accumulated HE work is uncommitted.
- Confirmed the established developer identity is
  `Markus.Liang <69946955+T-Markus-Liang@users.noreply.github.com>`.
- Configured the standard fork remotes: writable
  `origin=git@github.com:T-Markus-Liang/dimos_m20.git` and source
  `upstream=git@github.com:MeloLong/dimos.git`. The T-Markus-Liang account has
  no write access to MeloLong, so direct upstream push is intentionally avoided.
- Verified a dry-run push can create `origin/codex/he-orin`. Pushes use
  `GIT_LFS_SKIP_PUSH=1` because this is the intentional pointer-only clone and
  the upstream private LFS endpoint is not available.
- Audited the live Aurora node. It publishes RGB `bgr8`, depth `mono16`, IR
  `mono8`, PointCloud2, RGB CameraInfo and IR CameraInfo topics.
- Confirmed DimOS already provides native `Image`, `ImageFormat`, `CameraInfo`
  and `PointCloud2` types, so the bridge needs no new dependency.

## Decisions

- Preserve the already verified HE static deployment as a dedicated baseline
  commit before changing sensor architecture.
- Use a second focused commit for LD19 retirement and complete Aurora ingress.
- Keep Aurora streams local and bounded for Rerun; default ingress does not
  imply unbounded remote recording.
- Keep `HEConnection.enabled=False` and make no navigation/control change.

## Current State

- Existing HE static deployment and lifted control characterization pass.
- Current `HESensorBridge` still subscribes to LD19 and only optionally
  subscribes to the Aurora point cloud; it does not yet emit Aurora images or
  CameraInfo.
- Goal implementation is in progress. Real motion remains disabled.

## Resume Instructions

1. Read `dimos/robot/he/sensors.py`, `blueprints.py`, deployment verifiers and
   this log.
2. Verify the pushed baseline commit before changing Aurora behavior.
3. Implement and test all six Aurora outputs with no LD19 dependency.
4. Sync to Orin, disable the LD19 service, run resource/data gates, commit and
   push the sensor migration.

## Open Questions

- Aurora publishes no dedicated depth CameraInfo topic; determine whether its
  IR CameraInfo is the intended depth/IR calibration and document the driver
  limitation without inventing calibration data.
