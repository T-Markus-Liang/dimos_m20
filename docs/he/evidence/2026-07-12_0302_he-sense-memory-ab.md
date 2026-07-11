# HE Sense Rerun Memory A/B

## Scope

- Date: 2026-07-12 CST
- Platform: HE Jetson Orin NX 8GB
- Branch: `codex/he-orin`
- Profiler commit: `770a967a`
- 128MB candidate commit: `40c563a5`
- Service: `he-dimos-sense.service`
- Baseline: `he_sense_headless` Rerun `memory_limit="256MB"`
- Candidate: `he_sense_headless` Rerun `memory_limit="128MB"`

The service remained headless. No viewer, visual SLAM, planner,
`MovementManager` or control-output module was started. `HEConnection` remained
disabled and `/he/nav_cmd_vel` had zero publishers before and after both runs.

## Method

The 256MB service was already at steady state and was not restarted before its
baseline. The 128MB candidate was deployed through VM Git, pushed, pulled on
Orin with `git pull --ff-only`, and activated by restarting only
`he-dimos-sense.service`. Each variant used 11 one-shot profiler samples over at
least 10 minutes. Every sample captured the systemd cgroup, procfs memory
rollups, the largest anonymous mappings, process CPU/RSS, available memory,
swap, service restarts and Rerun port state.

Full runtime directories remain on Orin:

- `/home/ubuntu/he/logs/he-memory-ab/20260712_023031_256mb`
- `/home/ubuntu/he/logs/he-memory-ab/20260712_024859_128mb`

## Results

| Metric | 256MB | 128MB | Change |
| --- | ---: | ---: | ---: |
| cgroup memory median | 1001.395MiB | 870.500MiB | -130.895MiB (-13.1%) |
| cgroup memory maximum | 1006.922MiB | 872.691MiB | -134.231MiB |
| margin below 1GiB `MemoryHigh` at maximum | 17.078MiB | 151.309MiB | +134.231MiB |
| Rerun worker PSS median | 568.356MiB | 390.239MiB | -178.117MiB |
| Rerun private dirty median | 544.051MiB | 364.055MiB | -179.996MiB |
| Rerun largest anonymous mapping median | 410.953MiB | 222.871MiB | -188.082MiB |
| HESensorBridge PSS median | 164.346MiB | 172.933MiB | +8.587MiB |
| HESensorBridge CPU cumulative average | 51.6% | 52.5% | +0.9 percentage point |
| Rerun CPU cumulative average | 21.9% | 22.8% | +0.9 percentage point |
| available memory median | 3379.941MiB | 3511.859MiB | +131.918MiB |
| swap growth during run | 0 bytes | 0 bytes | unchanged |
| service restarts | 0 | 0 | unchanged |

The candidate retained the same eight latest-only Rerun entities and all
Aurora modalities. A 60-point-cloud-sample post-run diagnostic measured:

- RGB 14.599Hz
- depth 14.286Hz, median valid ratio 25.941%
- IR 14.925Hz
- point cloud 13.333Hz, 256000 points per frame
- IMU 46.820Hz
- RGB and IR/depth CameraInfo present

The 128MB run remained at 59.625-63.500C across the captured tegrastats sensor
temperatures. Port `9877` stayed listening and was reachable from macOS before
and after the soak. The final live sensor gate and independent read-only gate
passed; service status was active with `NRestarts=0` and no navigation process.

One combined diagnostic command produced a deliberate false-positive
localization warning because its own later `pgrep` arguments contained the
forbidden process names. Re-running the read-only gate as an isolated command
passed and confirmed no localization or navigation process was active.

## Decision

Keep the 128MB recording window for `he_sense_headless`. It materially reduces
the measured cgroup and Rerun anonymous memory while preserving the configured
entity surface, live sensor rates, remote Rerun endpoint and safety gates.

Do not apply this result to `he_teleop_headless`, `he_visual_slam_shadow` or the
global dedicated-worker policy. Those paths retain 256MB and require separate
resource evidence. This test proves live headless transport availability, not
a long-duration GUI rendering or playback workflow.

## Artifacts

- `2026-07-12_0240_he-sense-memory-256mb.json`
  SHA-256 `4257eed850bc64937d09a73c7d654062f0bea789b47fdf94abd53e3e6aae1d05`
- `2026-07-12_0259_he-sense-memory-128mb.json`
  SHA-256 `7f9a927cf62bc3b5f105d4d71a4f567a674eef640ed34b482ea98d954f30bd51`
- `2026-07-12_0300_he-sense-aurora-post.json`
  SHA-256 `51569e61b9c53ed6d282e6ffd427b4fbc1ace7c9d7da3f34c64bdc21c9be850e`
