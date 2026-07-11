# HE Dual-Path Shadow Soak

## Scope

- Date: 2026-07-12 CST
- Platform: HE Jetson Orin NX 8GB
- Branch: `codex/he-orin`
- Initial combined commit: `a6053859`
- Accepted optimized commit: `9c1588d0`
- Vehicle motion: prohibited

This test qualifies one motion-disabled DimOS coordinator running both:

- Aurora raw ROS directly into native RTAB-Map odometry and mapping; and
- Aurora sampled through `HESensorBridge` into a bounded latest-only Rerun.

The blueprint contains no `MovementManager`, `HEConnection`, follower or speed
publisher. `/he/nav_cmd_vel` was checked at every system sample.

## Initial Candidate Failure

The first combined blueprint used a 256MB Rerun window and four dedicated
Python modules. Worker policy expanded four configured workers to eight. A
10-minute run proved native SLAM and all sampled streams could coexist, but the
resource gate rejected the configuration:

- 14 tagged processes, about 1.43GiB PSS in a corrected tagged-process snapshot;
- minimum system available memory about 2.56GiB;
- 24.25MiB swap growth during the 11-point main loop;
- 84.25MiB runner-relative swap growth by the final health capture;
- `swap_growth_high` in all 251 final health samples.

The first process profiler used parent/child traversal and saw only two
processes because daemonized workers are reparented. That assertion failed only
after the full soak data had been captured; the EXIT trap stopped shadow and
restored Sense. A short repeat using `DIMOS_RUN_ID` environment tags found the
complete process set. This tagged method was used for every optimized sample.

The first run retained all sampled outputs from start to finish: image streams
about 3.7-4.0Hz, point cloud about 0.89Hz, CameraInfo about 0.96Hz and odom/IMU
about 16Hz. Function passed, but resource admission took precedence.

## Optimized Candidate

Two scoped changes were tested:

- `HERTABMapShadowRunner` shares the non-dedicated pool because its Python work
  is only native-process ownership and a 1Hz monitor. Native RTAB-Map remains in
  its own process group with unchanged stop and cleanup behavior.
- Combined Rerun uses the 128MB setting already qualified with the same eight
  sampled sensor entities. All fourteen sensor and visual entities remain
  latest-only.

The worker log confirmed three dedicated modules and six total workers.

## Optimized Results

| Metric | Result |
| --- | ---: |
| soak system samples | 11 over 10 minutes |
| tagged processes | 13 at every sample |
| total PSS min/median/max | 1312.9/1341.8/1350.7MiB |
| minimum available memory | 2.85GiB |
| median available memory | 2.86GiB |
| main-loop swap growth | 0 bytes |
| runner-relative swap growth | 0MB |
| native process-group RSS at end | 430.81MB |
| runtime status maximum age | 1.083s |
| temperature min/max | 62.218/66.750C |
| health samples | 259 |
| resource-health faults | 0 |
| navigation publishers | 0 at every sample |

Sampled DimOS stream rates remained present and bounded:

| Stream | Start | End |
| --- | ---: | ---: |
| RGB | 4.218Hz | 4.022Hz |
| depth | 4.129Hz | 3.755Hz |
| IR | 3.983Hz | 3.707Hz |
| point cloud | 0.883Hz | 0.836Hz |
| RGB CameraInfo | 0.969Hz | 0.973Hz |
| depth CameraInfo | 0.969Hz | 0.973Hz |
| odom | 16.088Hz | 16.174Hz |
| IMU | 16.027Hz | 15.933Hz |

Health retained the known `map_known_ratio_low` reason in all samples. Three
samples briefly added `pose_stale`; maximum pose age was 0.531s against the
0.5s gate, and each transition recovered automatically. There was no tracking
loss or runtime/resource fault. This transient remains a load/robustness signal
for longer and moving tests, not permission to relax the freshness threshold.

The optimized shadow stopped with ordinary SIGTERM and left no traceback,
SIGKILL, OOM or native residue. The EXIT path restored `he-dimos-sense`.
Post-restore RGB/depth/IR were 12.66/14.08/14.29Hz, point cloud contained
256000 points, both CameraInfo streams were present, Sense had zero restarts,
the remote `9877` port was reachable and the independent read-only gate passed.

## Decision And Boundary

Keep the optimized six-worker, 128MB dual-path shadow. It closes the static
functional and resource regression introduced by combining HESensorBridge with
native SLAM.

This does not approve navigation or moving SLAM. The static map remains below
quality admission, and physical calibration, moving ATE/RPE, dynamic tracking,
loop closure and displaced-start relocalization remain open. Sense and shadow
also remain mutually exclusive coordinators; the shadow now contains both data
paths internally, but separate systemd service isolation for SLAM and Rerun is
not claimed.

## Artifacts

- `2026-07-12_0346_dual-path-v1-summary.json`
  SHA-256 `5e46945dde472e514eada6917a892f8d303b55b7019c83dedee82c7b2ee7b6d7`
- `2026-07-12_0409_dual-path-v2-summary.json`
  SHA-256 `dabcbef14b64a73b164601bf22664f4def981a5bf5dd19191c947a42f5e16b7f`
- `2026-07-12_0409_dual-path-v2-health.json`
  SHA-256 `ee146d3bbabfeaf53c95e51cedb7ea20f7dbd5f59c1396b3c99115954eedd8a0`
- `2026-07-12_0409_dual-path-v2-runtime.json`
  SHA-256 `b6d3c7e67f373bc7243270b63aefc48e47bbd58f6b52b4e746072e51786e015d`

Complete raw runtime directories remain on Orin:

- `/home/ubuntu/he/logs/he-dual-path-20260712`
- `/home/ubuntu/he/logs/he-dual-path-v2-20260712`
