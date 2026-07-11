# HE DimOS Visual SLAM Shadow Soak

Date: 2026-07-11 14:48-15:05 CST

## Integrated Run

Commit `e4d469cb` started `he-visual-slam-shadow` with five modules and no
motion module. The first run stayed active for about three minutes. It emitted
visual odometry, occupancy, path, status, dynamic TF and structured DimOS
health. `/he/nav_cmd_vel` had zero publishers throughout.

Observed steady state:

- available system memory: about 3.33GiB;
- RTAB-Map process-group RSS reported by health: about 493-533MiB;
- generated database after the first run: about 11MiB;
- odometry latency after the health fix: about 138ms in the sampled status;
- map known ratio: 2.04-2.31%;
- map free ratio among known cells: 12.7-15.0%;
- no bad-sync, missing-TF, OOM or exception log in the clean fresh-database run;
- planner-facing `global_costmap` was withheld.

Health was correctly unhealthy because of `map_known_ratio_low`. Runtime RSS
remained below the 768MiB health threshold.

## Defects Found And Fixed

`OdomInfo` originally replaced the bridge tracking dictionary and discarded
the measured `odom_latency_ms`. Commit `651af9bb` changed it to merge tracking
fields and increased the TF age threshold from 0.5s to 1.0s for the measured
6Hz estimator.

The original runner reused `/var/tmp/he-rtabmap/rtabmap.db`. Visual odometry
restarted from zero while the incremental database retained an older graph.
Loading the 25MiB database then caused RTAB-Map 0.23.7 to abort in
`Memory::addLink()` with an invalid node-weight condition.

The runner also polled children using `kill -0`. A crashed child remained a
zombie until reaped, so the shell incorrectly treated it as alive and left
odometry running. Concurrent test attempts then exposed multiple orphaned
odometry processes. All were stopped before continuing.

Commit `3da830d3` fixed the lifecycle:

- `wait -n` reaps the first child that exits and triggers sibling cleanup;
- a file lock and process check reject concurrent HE shadow instances;
- a fresh timestamped database is used by default;
- only four prior generated databases plus the current database are retained;
- resume requires an explicit `HE_RTABMAP_DB`;
- core dumps are disabled;
- Linux parent-death signaling asks the runner to clean up if its DimOS worker
  is forcibly terminated.

## Fault Injection

The post-fix run used
`/var/tmp/he-rtabmap/rtabmap-20260711-150344.db`. A concurrent invocation was
immediately rejected. After more than 30 seconds without fatal errors, the
SLAM child was deliberately sent SIGTERM.

Within six seconds:

- both RTAB-Map SLAM and RGB-D odometry were gone;
- no native ROS SLAM process remained;
- periodic health reported `slam_process_down`, stale pose/TF and the existing
  map quality failure;
- runtime RSS in health dropped to zero;
- `/he/nav_cmd_vel` remained at zero publishers.

## Remaining Runtime Rough Edge

Normal `dimos stop` waits five seconds on `RerunBridgeModule` before worker
shutdown begins, so the CLI escalated the main daemon to SIGKILL. Native SLAM
children were still removed, and a forced stop after fault injection left no
ports or processes. This is an existing DimOS/Rerun coordinator shutdown issue
that should be fixed before production service activation.

After testing, `he-dimos-sense.service` was restored active with zero restarts.
Real motion remained disabled for the entire soak.
