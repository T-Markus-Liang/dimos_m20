# HE Visual Shadow Graceful Shutdown

Date: 2026-07-11 21:28 CST

Status: root cause fixed on VM; Orin lifecycle verification pending

## Safety Scope

This work changes only shutdown ownership for `he-visual-slam-shadow`. The
blueprint still contains no `MovementManager`, `HEConnection` or command
publisher. No motion test is required or permitted.

## Corrected Root Cause

The earlier shutdown timeout was attributed to `RerunBridgeModule`. Timestamped
worker logs disprove that attribution. On the final bounded soak shutdown:

- all workers received their stop request at about `13:15:44.02Z`;
- `RerunBridgeModule` reported stopped at `13:15:44.09Z`, about 73ms later;
- `HEVisualMapAdapter` stopped at about 81ms;
- `HEVisualSlamBridge` stopped at about 265ms;
- the RTAB-Map runner did not report module completion before the parent grace
  period ended.

The shell runner sent SIGINT and then called `kill -0` in ten 200ms loops for
each of three children. Exited-but-unreaped children remain visible to
`kill -0`, so the cleanup could spend about 2.5 seconds per zombie and exceed
the CLI's global five-second SIGTERM grace period.

## Fix

Cleanup now signals all three children in parallel:

1. SIGINT to permit RTAB-Map database cleanup;
2. one shared 1.5-second grace;
3. SIGTERM and one shared 0.5-second grace;
4. SIGKILL only for survivors;
5. `wait` for all children so no zombie remains.

An external SIGINT or SIGTERM uses the same cleanup and exits successfully.
The Python process-group owner now waits three seconds before its SIGKILL
fallback and one second for final reap, keeping its worst-case local path below
the five-second CLI boundary.

The HE lifecycle test suite now starts a real isolated process group and proves
that `_stop_process_group()` reaps it within 4.5 seconds. All 39 HE tests, Ruff,
Bash syntax and `git diff --check` pass on the VM.

## Required Orin Evidence

After commit and fast-forward sync, start the motion-free shadow blueprint,
wait for both native processes and `/he/visual_odom`, then use normal
`dimos stop` without `--force`. Record elapsed time and require:

- CLI reports `Stopped with SIGTERM`, not escalation to SIGKILL;
- elapsed stop time is below five seconds;
- no native odometry, SLAM, watchdog, Rerun port or DimOS process remains;
- `he-dimos-sense` restores active with zero restarts;
- the independent read-only gate passes and navigation publishers remain zero.
