# Compare WD And Ivan M20 Source

## Metadata

- Date: 2026-07-10 22:41 CST
- Session id: current Codex desktop thread
- Project: dimos-wd-m20
- Workspace: `/home/markus/work/dimos_wd_m20` and `/home/markus/work/dimos_m20` on VM `autoware-180`
- Task: compare the WD tested branch source with the existing Ivan/Dan development workspace
- Status: completed
- Branch if relevant: `feat/wd/m20` versus `feat/ivan/m20`

## User Request Summary

Inspect and explain the source-code differences between `/home/markus/work/dimos_wd_m20` and `/home/markus/work/dimos_m20`.

## Work Done

- Confirmed repository branches, HEAD commits, remotes, and worktree status.
- Separated committed branch differences from local uncommitted changes in the Ivan workspace.
- Confirmed Ivan HEAD `c49481b440ccc9b7f1bab7c4b4e69a7592c58263` is the merge-base and direct ancestor of WD HEAD `98713d97341bc9392e5dd531b1c13aaf98782a23`; WD is 94 commits ahead and Ivan HEAD has zero unique commits.
- Compared tracked trees by path and blob hash:
  - Ivan HEAD: 1628 files.
  - WD HEAD: 1811 files.
  - WD-only paths: 225.
  - Ivan-only paths: 42.
  - Common paths with changed content: 143.
  - Overall committed diff: 373 files, 39,271 insertions, 6,313 deletions.
- Confirmed the current Ivan worktree's `dimos/navigation/dannav` directory is byte-for-byte identical to the committed WD DanNav directory, excluding `__pycache__`.
- Inspected M20 blueprints, real-robot connection wiring, native sensor modules, map-save tools, fixed-path debug planner, navigation reports, Rerun bridge, WebSocket command-center, simulation integration, and dependency changes.
- Runtime-import tested WD `dimos.robot.deeprobotics.m20.nav.m20_dan_nav` using the existing VM environment. WD HEAD fails with `NameError: _m20_dan_rerun is not defined` at line 109.
- Traced that regression to merge commit `98713d97`: one merge parent retained `_m20_nav_rerun_config` while the resolved code referenced `_m20_dan_rerun`.

## Decisions

- Compare committed snapshots and effective worktrees separately so local Dan/Web/MuJoCo changes are not misattributed to `feat/ivan/m20` itself.
- Exclude runtime logs, build outputs, virtual environments, LFS payloads, and Codex session logs from source comparison.
- Treat the WD branch as a newer integration line rather than a small M20-only patch because it also contains 94 upstream/main commits and broad framework changes.
- Do not modify either source tree during this comparison.

## Current State

- WD is the newer committed baseline and includes the tested Dan controller implementation plus substantial M20 real-robot integration.
- Ivan's current worktree has the same DanNav implementation, but its M20 assembly, simulation path, LAN Web viewer, and 2D point-cloud projection are local changes not present in WD.
- WD adds M20-specific `m20-dan-nav`, `m20-map-save`, `m20-true-simple-nav`, fixed-path debug planning, odometry conversion, native C++ camera/lidar modules, and test reports.
- WD's dedicated Dan blueprint uses 0.05m voxels, 1.0m overhead clearance, 0.55m wall clearance, 0.15m step threshold, `lock_replan=1.0`, and `run_profile="walk"`. Ivan's local blueprint uses 0.1m voxels, 0.6m robot height, 0.2m wall clearance, 0.25m step threshold, no replan lock, and the same walk profile.
- WD Rerun adds per-entity clear/latest-only behavior and detailed stream/FPS statistics. Ivan instead adds LAN/CORS, `newest_first`, dynamic dashboard URLs, and a command-center `/local_map` -> 2D costmap adapter.
- WD HEAD currently cannot import `m20-dan-nav` because of the merge regression above; the pre-merge commits `fcdce515` and `73683fec` use `vis_module(..., rerun_config=_m20_nav_rerun_config)` and do not contain this unresolved symbol.

## Resume Instructions

1. Read this log.
2. Re-check both repository statuses before any merge or cherry-pick work.
3. If adopting WD as the new baseline, first repair or select a pre-merge version of `m20_dan_nav.py`, then port only the Ivan simulation and Web/LAN improvements that are still wanted.
4. Do not blindly copy the full Ivan blueprint over WD because that would discard WD's real-robot topic naming, odometry adapter, tuned physical clearances, replan lock, map-save, and native sensor work.

## Open Questions

- Confirm which exact WD commit/worktree was used for the internally successful test; current remote HEAD has a merge-time import regression.
