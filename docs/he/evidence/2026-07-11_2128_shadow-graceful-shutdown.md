# HE Visual Shadow Graceful Shutdown

Date: 2026-07-11 21:28 CST

Status: daemon/non-parent worker cleanup fix pending final Orin verification

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

## Third Live Attempt And Daemon Parent Mismatch

Commit `37bb0f78` was fast-forwarded to Orin. The third normal stop no longer
needed SIGKILL:

- the CLI reported `Stopped with SIGTERM`;
- elapsed stop time was 4926ms;
- no native RTAB-Map process or Rerun port remained.

This proves that synchronous caller-backend cleanup was the five-second host
blocker. The attempt was not clean, however: six worker shutdowns logged
`AssertionError: can only join a child process`.

The workers are created before `daemonize()` performs its double fork. The
resulting daemon process inherits `multiprocessing.Process` objects but is not
their recorded parent, so `Process.join()` is invalid there. The correction
uses `multiprocessing.join()` only in the original parent. A daemon/non-parent
waits for the same PID with the existing `psutil` dependency, preserving the
five-second graceful wait and the SIGTERM/SIGKILL fallback without raising.
The run registry now also treats a zombie PID as exited instead of reporting a
stale run as alive.

The RPC cleanup thread receives a bounded 100ms join. This keeps ordinary test
cleanup deterministic while preserving nonblocking stop behavior under a busy
LCM backend. The focused parent/non-parent, zombie registry and RPC tests raise
the related core selection to 49 passing tests; all 39 HE tests, Ruff and
`git diff --check` also pass on the VM.

## Fourth Live Attempt And Duplicate Coordinator Stop

Commit `7dae71b6` removed the non-parent assertion and passed focused checks on
Orin. The motion-free shadow stack started correctly, `/he/visual_odom` emitted,
and `/he/nav_cmd_vel` retained zero publishers. Normal stop still escalated:

- CLI elapsed time was 7111ms and reported SIGKILL escalation;
- no process or port remained afterward;
- no child-process assertion or worker-shutdown error was logged.

Timestamped logs show the first shutdown was healthy. All module stop RPCs and
all six workers completed from `14:06:08.520Z` through `14:06:10.968Z`, about
2.45 seconds. The signal handler then called the tagged-process sweep before
the daemon could exit. Python's multiprocessing `resource_tracker` ignores
SIGTERM and normally exits when the parent closes its pipe, so that pre-exit
sweep consumed its full two-second grace. `sys.exit()` then unwound through
`ModuleCoordinator.loop()` and its `finally` called `stop()` a second time.

The correction removes the redundant pre-exit sweep from the signal handler.
The already-running independent watchdog waits for the main PID to disappear
and retains the tagged-process sweep for genuine orphans. Coordinator stop is
now lock-protected and idempotent, so signal shutdown and loop unwinding cannot
repeat module or manager cleanup. A focused idempotence test raises the related
core selection to 50 passing tests; all 39 HE tests and static checks pass on
the VM. Final Orin verification remains required.

## Fifth Live Attempt And Timing Margin

Commit `1d2dcf6a` passed the functional graceful-stop gate on Orin:

- CLI reported `Stopped with SIGTERM` with no escalation;
- no child-process assertion, worker error or traceback was logged;
- exactly five module stops and one worker-manager shutdown were logged;
- no DimOS, native SLAM, watchdog or Rerun port remained;
- `/he/visual_odom` emitted and `/he/nav_cmd_vel` had zero publishers before stop.

The end-to-end CLI command measured 5228ms, despite coordinator cleanup itself
completing in about 2.52 seconds. Each of five module stop RPCs still reserved
up to 100ms for caller-backend cleanup, consuming about 0.5 seconds of avoidable
margin. That observation window is reduced to 10ms. This retains an opportunity
for immediate cleanup while preserving the intended nonblocking behavior under
load. The focused RPC threshold returns to 100ms; the same 50 core tests, 39 HE
tests and static checks pass on the VM. One final Orin timing run is pending.

## Required Orin Evidence

After the reduced RPC cleanup-window commit and fast-forward sync, start the
motion-free shadow blueprint, wait for both native processes and
`/he/visual_odom`, then use normal
`dimos stop` without `--force`. Record elapsed time and require:

- CLI reports `Stopped with SIGTERM`, not escalation to SIGKILL;
- elapsed stop time is below five seconds;
- no `can only join a child process` or `Error shutting down worker` log;
- no native odometry, SLAM, watchdog, Rerun port or DimOS process remains;
- `he-dimos-sense` restores active with zero restarts;
- the independent read-only gate passes and navigation publishers remain zero.
