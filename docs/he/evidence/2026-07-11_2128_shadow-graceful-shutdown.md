# HE Visual Shadow Graceful Shutdown

Date: 2026-07-11 21:28 CST

Status: child and host RPC cleanup fixes pending final Orin verification

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

## First Live Attempt And Remaining Cause

Commit `f6fbfb25` passed 39 tests and was deployed to Orin, but the first normal
stop still failed: the CLI escalated after 7.099 seconds. The result disproved
that child cleanup was the only blocker.

The new timestamped log is more specific:

- the daemon received SIGTERM at `13:32:58.856Z`;
- the coordinator began the `RerunBridgeModule.stop()` RPC at `13:32:58.881Z`;
- no RPC completion arrived before the five-second CLI deadline;
- after parent escalation, the worker's direct shutdown began at
  `13:33:03.904Z` and Rerun itself stopped about 1.2ms later.

Rerun shutdown is therefore fast once invoked locally, but its stop RPC is
starved while the bridge continues processing visual messages. The shadow
blueprint previously placed Rerun last, so reverse-order coordinator shutdown
tried to stop it first while RTAB-Map and all adapters were still publishing.

The second fix makes Rerun the first module started and last stopped. The native
runner is now last started and first stopped, cutting the source before bridge
shutdown. A blueprint-order test locks this lifecycle contract while retaining
the same five motion-free modules and connections.

That ordering deployed correctly, but the second normal stop still escalated in
6.971 seconds. It did stop the native runner first as intended, so the remaining
five-second delay could no longer be attributed to Rerun load or module order.

Core inspection found the host-side defect. `RpcCall.stop()` correctly publishes
the remote stop with `call_nowait`, because a module closes its own RPC service
before it can reply. It then synchronously called `stop_rpc_client()`, whose
local LCM service can spend the full five seconds joining its handler thread.
The coordinator was blocking on shutdown of its own caller backend, not waiting
for the remote module.

The third fix preserves synchronous publication of the stop request but closes
the caller backend on a named daemon thread. Exceptions remain logged. A core
test deliberately blocks client cleanup and proves that the stop call returns
in under 100ms, cleanup starts, and the thread exits after release. The related
36 core lifecycle/CLI tests and all 39 HE tests pass.

## Required Orin Evidence

After the core RPC commit and fast-forward sync, start the motion-free shadow blueprint,
wait for both native processes and `/he/visual_odom`, then use normal
`dimos stop` without `--force`. Record elapsed time and require:

- CLI reports `Stopped with SIGTERM`, not escalation to SIGKILL;
- elapsed stop time is below five seconds;
- no native odometry, SLAM, watchdog, Rerun port or DimOS process remains;
- `he-dimos-sense` restores active with zero restarts;
- the independent read-only gate passes and navigation publishers remain zero.
