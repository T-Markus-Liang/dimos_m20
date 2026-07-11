# HE Depth Quality Localization Health

Date: 2026-07-12

Candidate commit: `d8650a7ff`

Safety state: vehicle motion disabled, `HEConnection.enabled=False`, and
`/he/nav_cmd_vel` had zero publishers throughout.

## Change Under Test

`HESensorBridge` now computes three coverage ratios after its existing 5Hz
depth conversion: global, center 40% and bottom third. It publishes only those
ratios and the source timestamp as `depth_quality`. `HELocalizationHealth`
rejects missing, malformed, older-than-1s or below-10% regional evidence.

The coordinator connected both endpoints over `pLCMTransport` on
`/depth_quality`. The health worker did not receive a full depth image and no
additional ROS subscription was created.

## Live Static Result

A 45-second shadow capture retained 906 health samples:

| Metric | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: |
| global valid depth | 25.35% | 26.03% | 26.56% |
| center-40% valid depth | 18.61% | 19.16% | 19.80% |
| bottom-third valid depth | 4.41% | 5.64% | 6.60% |

All 906 samples contained `depth_bottom_coverage_low`; none contained the
global or center low-coverage reasons. All also retained the existing map
quality rejection. Six transient `pose_stale` samples recovered automatically.
Maximum depth-quality age was 0.433s, below the 1s limit.

This is the intended distinction: the camera is producing timely depth and
adequate global/center coverage for this provisional gate, but the known lower
field defect remains an explicit independent reason even while RTAB-Map emits
pose.

## Outage And Recovery

During a second shadow run, `aurora930.service` was stopped for 4 seconds and
then restarted while health was recorded for 40 seconds:

- `depth_quality_stale` first appeared 0.859s after service stop;
- its last sample was 3.070s after service restart;
- the final depth-quality age was 0.022s;
- final global/center/bottom ratios were 25.75/19.25/5.14%;
- final reasons were only `depth_bottom_coverage_low` and
  `map_known_ratio_low`.

The same interval produced expected pose, TF and CameraInfo freshness reasons.
The independent shadow gate passed after recovery. No threshold was relaxed.

## Resource And Lifecycle Result

At the end of the static capture:

- shadow cgroup memory was 1408MiB with 353 tasks and zero restarts;
- throttle memory was about 25MiB with zero restarts;
- system available memory was about 2.78GiB;
- swap rose 8.75MiB during shadow transition and then stayed at 580MiB across
  all tegrastats samples;
- tegrastats RAM was 4572-4714MiB, GR3D peaked at 11%, and Tj at 64.718C.

Both runs returned through the normal mode wrapper. Final state was Aurora,
Sense and throttle active with zero restarts, shadow inactive, no native SLAM
residue, and deployment-integrity/read-only gates passing.

## Readiness Admission Hardening

The shadow gate now validates its three-second live health report with the same
`validate_shadow_health_report` function used by deterministic tests. It rejects
runtime pressure plus missing, invalid or stale depth evidence, and verifies
that every sample has a finite 0-1s age and finite `[0,1]` global/center/bottom
ratios. Known low coverage is deliberately not an admission error because the
shadow must remain available to observe unhealthy state.

Tests prove that a complete sample containing only
`depth_bottom_coverage_low` is admitted, while `depth_quality_stale`,
`depth_quality_missing`, `slam_memory_high`, age 1.1s and missing ratio fields
are rejected. The previously captured real outage supplied the live stale
transition; no production fault override was added.

After deployment, the standard wrapper completed live admission in 42 seconds
and returned status 0. A second independent gate also passed. Shadow cgroup
memory was 1217MiB at admission and 1354MiB at the second check; swap stayed at
580MiB and both shadow/throttle restart counts were zero. Normal return restored
Sense and passed final deployment/read-only gates.

## Evidence

- `2026-07-12_0723_depth-quality-health.json`, SHA-256
  `58689d2e7c4ab34a8bada1292750cb0ce0b983af9d4d03334e488dee2fb20214`
- `2026-07-12_0726_depth-quality-outage.json`, SHA-256
  `f07e54c78e92c732042d98156e59281b8360aea8991195f925fa3d38f912e749`

## Decision Boundary

Accept the direct depth-quality health path for shadow operation. The 10%
regional limits are conservative interlocks, not proof that depth is suitable
for navigation. The current bottom-third result remains failed. Matte-target,
camera pitch/height, direct USB3, vendor specification and moving-map evidence
are still required before changing thresholds or enabling navigation.
