# HE Planner-map Withholding Qualification

Date: 2026-07-12

Commit: `fba24dd185319e189ae010948bd1dd245bb0ec6d`

Mode: static integrated RTAB-Map shadow; vehicle motion disabled

## Purpose

Prove on the live Orin graph that RTAB-Map can produce the internal
`/visual_map` while continuously unhealthy localization prevents any
planner-facing `/global_costmap` output.

## Method

The read-only diagnostic subscribed before shadow startup so it could observe
the non-latched LCM map publication. It collected for 90 seconds while the
standard mode wrapper started shadow and passed its unchanged admission gate.
The collector retained receipt timestamps and health reasons only, not map
payloads, and published no messages.

An earlier 30-second attempt started after shadow had stabilized and correctly
failed with `no visual map was received`. The service log showed that the one
stationary map had already been published and withheld. This was a subscriber
timing issue, not permission to treat missing evidence as success.

## Result

- `/visual_map`: 1 message
- `/localization_health`: 1172 samples
- healthy samples: 0
- unhealthy samples: 1172
- `/global_costmap`: 0 messages
- dominant reasons: `depth_bottom_coverage_low` 1167,
  `map_known_ratio_low` 1063
- startup-only fail-closed reasons were also captured before all sources became
  ready; none produced a healthy sample
- standard and independent shadow read-only gates: PASS
- independent shadow cgroup memory: 1389 MiB
- swap: 580 MiB before, during and after the test
- Aurora, shadow and point-cloud-throttle restart counts: 0
- `/he/nav_cmd_vel` publishers: 0

Raw machine-readable evidence:
`2026-07-12_0800_planner-map-withholding.json`.

## Final State

The normal Sense mode was restored. `aurora930`, `he-dimos-sense` and
`he-pointcloud-throttle` are enabled and active; `he-dimos-shadow` is static and
inactive. Deployment integrity and the final read-only gate passed. No
`rtabmap`, `rgbd_odometry` or database-watchdog process remained.

This proves the static live withholding path only. It does not approve map
quality, localization, moving operation or navigation.
