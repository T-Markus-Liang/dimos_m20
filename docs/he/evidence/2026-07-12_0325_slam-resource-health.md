# HE Shadow Resource Health Qualification

## Scope

- Date: 2026-07-12 CST
- Platform: HE Jetson Orin NX 8GB
- Branch: `codex/he-orin`
- Implementation commit: `bf5f8215`
- Vehicle motion: prohibited; `/he/nav_cmd_vel` remained at zero publishers
- Runtime: RTAB-Map 0.23.7 mapping shadow

This qualification verifies that real runner resource evidence reaches
`HELocalizationHealth`, an intentionally raised available-memory threshold
fails closed, and restoring the default threshold clears only that resource
reason. It does not qualify moving localization or navigation.

## Runtime Contract

`HERTABMapShadowRunner` publishes once per second:

- native process-group `rss_mb`;
- system `MemAvailable` as `system_available_mb`;
- current `swap_used_mb`;
- non-negative `swap_growth_mb` relative to runner startup.

Health rejects runtime status older than 2.5s, malformed resource values, RSS
above 768MB, available memory below 1024MB, or swap growth above 64MB.

## Procedure

The first attempt tried to start the shadow while the normal
`he-dimos-sense.service` coordinator was active. It failed before RTAB-Map or a
database started because the current DimOS Coordinator RPC is host-global and
allows only one coordinator on the LCM bus. There was no OOM or navigation
process residue.

The verified procedure used one shell with an EXIT restore trap:

1. Pass the read-only gate.
2. Stop only `he-dimos-sense.service`.
3. Start a fresh mapping shadow with
   `helocalizationhealth.min_system_available_mb=8000`.
4. Capture five runtime samples and ten seconds of localization health.
5. Stop normally with SIGTERM.
6. Start a second fresh shadow with the default 1024MB threshold.
7. Capture the same evidence and stop normally with SIGTERM.
8. Restore `he-dimos-sense.service`, then pass live-sensor and read-only gates.

An initial orchestration attempt exited while sourcing ROS because Bash
`nounset` is incompatible with the Humble setup script. Its EXIT trap restored
Sense and passed the read-only gate. The successful run omitted `nounset` but
retained `errexit`, `pipefail` and the restore trap.

## Results

| Metric | Forced 8GB threshold | Default 1GB threshold |
| --- | ---: | ---: |
| runtime samples | 5 | 5 |
| health samples | 184 | 187 |
| RSS latest | 435.199MB | 433.770MB |
| available latest | 3287.203MB | 3301.480MB |
| swap used latest | 548.523MB | 548.523MB |
| swap growth latest | 0MB | 0MB |
| maximum runtime status age | 1.074s | 1.078s |
| `system_memory_low` samples | 184 | 0 |
| `map_known_ratio_low` samples | 184 | 187 |

The forced run had exactly `system_memory_low + map_known_ratio_low`. The
default run cleared `system_memory_low` and retained only the known existing
poor-map reason. Neither run reported stale/invalid runtime, RSS high, swap
invalid/high, process down or navigation output. Both stopped with ordinary
SIGTERM without traceback, SIGKILL, OOM or native residue.

After restoration, Aurora RGB/depth/IR were 15.50/10.26/15.62Hz, the point cloud
contained 256000 points, both CameraInfo streams were present and depth validity
was 26.1%. Sense was active with zero restarts and about 876MiB cgroup memory.
The final independent read-only gate passed.

## Decision And Remaining Gap

Accept the runtime resource health contract for static shadow use. The live
fields, configured fault, restored default behavior, graceful stop and safety
restore are proven.

Do not claim the full dual-path architecture is complete. Because Coordinator
RPC is host-global, the current complete Sense and shadow blueprints cannot run
as two concurrent DimOS coordinators. This test temporarily replaced Sense with
shadow. A later architecture change must provide simultaneous full-rate local
SLAM and sampled Aurora Rerun output with independent bounded resources before
the phase-H acceptance criterion is closed.

## Artifacts

- `2026-07-12_0321_slam-resource-forced-runtime.json`
  SHA-256 `ae851e636071bc2b77943f65e389783c0ffdf4aa8f193591339bdd82f85c6bff`
- `2026-07-12_0321_slam-resource-forced-health.json`
  SHA-256 `788c4fd9594182df67576159c3175b6acb011716a0ea2cc27354db388f168fb0`
- `2026-07-12_0322_slam-resource-normal-runtime.json`
  SHA-256 `616963c7f709f1328b7222cc7596e3154c5a7a41a3d6c60664a77e1e6e2150d2`
- `2026-07-12_0322_slam-resource-normal-health.json`
  SHA-256 `11e38205b02b508c6cfb3bf276a0f5e7e70adc9849d8629eda8cef0974d7671f`

Complete runtime files remain under
`/home/ubuntu/he/logs/he-resource-health-20260712`.
