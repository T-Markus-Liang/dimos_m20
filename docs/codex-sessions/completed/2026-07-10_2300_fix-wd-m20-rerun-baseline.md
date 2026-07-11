# Fix WD M20 Rerun Baseline

## Metadata

- Date: 2026-07-10 23:00 CST
- Session id: current Codex desktop thread
- Project: dimos-wd-m20
- Workspace: `/home/markus/work/dimos_wd_m20` on VM `autoware-180`
- Task: repair the WD M20 Dan navigation import regression, designate WD as the primary development baseline, and compare WD versus Ivan Rerun behavior
- Status: completed
- Branch if relevant: `feat/wd/m20`

## User Request Summary

Fix `NameError: name '_m20_dan_rerun' is not defined`, use WD M20 as the continuing development baseline, and explain the exact Rerun configuration differences from the Ivan workspace.

## Work Done

- Identified the merge regression and selected the minimal pre-merge-compatible repair: use the existing `_m20_nav_rerun_config` through `vis_module` and `global_config.viewer`.
- Updated `dimos/robot/deeprobotics/m20/nav/m20_dan_nav.py`:
  - restored the `global_config` import;
  - restored the `vis_module` import;
  - replaced undefined `_m20_dan_rerun` with `vis_module(viewer_backend=global_config.viewer, rerun_config=_m20_nav_rerun_config)`.
- Verified `git diff --check` and Python compilation.
- Verified direct import of `dimos.robot.deeprobotics.m20.nav.m20_dan_nav` succeeds.
- Verified registry loading through `get_blueprint_by_name("m20-dan-nav")` succeeds.
- Ran focused DanNav tests for path speed profile, command limits, run envelope, and local planner: 11 passed.
- Updated the global project registry so `/home/markus/work/dimos_wd_m20` is the primary M20 development/deployment baseline and `/home/markus/work/dimos_m20` is a legacy migration/comparison source.
- Compared the actual WD `m20-dan-nav` Rerun config, WD bridge capabilities, WD generic M20 Rerun config, and Ivan current Rerun config.

## Decisions

- Preserve the WD branch's current Rerun config values and real-robot blueprint structure; fix only the broken assembly symbol.
- Treat `/home/markus/work/dimos_wd_m20` as the primary M20 development baseline after verification.
- Do not change Rerun rates or retention semantics in this fix; surface the observed configuration hazards separately for an explicit follow-up decision.

## Current State

- NameError is fixed in the WD worktree; the only source modification is `m20_dan_nav.py` with 3 insertions and 1 deletion.
- WD is now registered as the primary M20 baseline.
- WD dedicated `m20-dan-nav` currently configures `memory_limit="1GB"`, camera `max_hz=0`, map rates 1Hz/2Hz, path display overrides, default message timestamps, and no active `latest_only_entities` or debug stats.
- In the WD bridge implementation, `max_hz=0` means no throttle because only positive values create intervals; it does not disable camera logging.
- WD generic `basic.py:rerun` is a different configuration: 2GB, cameras 20Hz, map 1Hz/2Hz, latest-only clears for point/map entities, message timestamps disabled, and detailed stream/FPS diagnostics.
- Ivan current M20 Rerun is 1GiB, cameras 1Hz, map 1Hz/2Hz, `newest_first=True`, LAN CORS support, and no WD latest-only/debug features.
- WD latest-only is implemented as `rr.Clear(recursive=True)` followed by `rr.log`; it controls current entity state but does not provide a strict recording TTL or fixed-duration history window.

## Resume Instructions

1. Read this log and the completed comparison log.
2. Continue all M20 development from `/home/markus/work/dimos_wd_m20`.
3. Before production viewer testing, decide whether camera `max_hz=0` should mean disabled or should be replaced with an explicit positive live rate.
4. Decide whether to port Ivan's LAN/CORS/newest-first behavior and lightweight 2D command-center adapter into WD.

## Open Questions

- Desired WD `m20-dan-nav` camera rate and whether camera entities should be completely excluded from Rerun.
- Whether WD should use per-entity Clear, newest-first delivery, or a separate bounded web-live path; these solve different problems.
