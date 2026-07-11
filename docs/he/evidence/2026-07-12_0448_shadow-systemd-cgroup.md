# HE Shadow Systemd Cgroup Qualification

Date: 2026-07-12 04:27-04:46 CST

Platform: HE Jetson Orin NX 8GB

Branch: `codex/he-orin`

Commits tested: `69993559457dcd38b0a52e75eb395237a58bc617` and readiness fix
`951d1108f21edd56ada8f47b17f40e9a553010ca`

## Scope

Qualify the integrated dual-path visual-SLAM shadow as a static systemd mode
without enabling any navigation or chassis command output. Verify whole-cgroup
resource limits, zero OOM/restarts, bounded swap behavior, normal cleanup, and
restoration of the normal Sense service.

## Installed Contract

- `he-dimos-sense.service`: enabled and normal boot mode.
- `he-dimos-shadow.service`: static and inactive until an explicit switch.
- Reciprocal `Conflicts=` prevents concurrent DimOS coordinators.
- Shadow: `Restart=no`, `MemoryHigh=2G`, `MemoryMax=2560M`,
  `OOMPolicy=stop`, and `TasksMax=512`.
- The shadow gate requires zero `/he/nav_cmd_vel` publishers, no motion/GUI/
  simulation process, live native RTAB-Map processes, bounded resource health,
  and the expected sampled sensor subscribers.

## Ten-Minute Soak

The service ran from the admitted shadow state while 11 samples were collected
at one-minute intervals from the systemd cgroup and ROS graph.

| Metric | Result |
| --- | --- |
| Cgroup memory | 1346.7/1359.0/1366.7MiB min/median/max |
| Margin below `MemoryHigh` | at least 681.3MiB |
| Tasks | 349 at every sample; limit 512 |
| `memory.events` high/max/oom/oom_kill | 0/0/0/0 at every sample |
| Service restarts | 0 |
| System available memory | 3011.9-3040.7MiB |
| System swap used | 558.0MiB at start and end; zero growth |
| Navigation publishers | 0 at every sample |
| Average cgroup CPU | about 1.66 cores over the sampled interval |
| Maximum sampled temperature | 66.187C |
| Journal warning/error entries | none |

The shadow-specific read-only gate passed both at initial admission and after
the soak. Native runtime health had no stale, invalid, memory-low, memory-high,
or swap-growth reason. The start/end profiler snapshots are retained beside
this report:

- `2026-07-12_0429_shadow-service-start.json`, SHA-256
  `32673107e25e5700345331390a13b63d1187b95417af9f9c50099a5c28f3fac5`;
- `2026-07-12_0439_shadow-service-end.json`, SHA-256
  `d6053a9cf1b61400b6e9811718fc6d84654857a6704daaaf559a53835b6cd2df`.

## Return-To-Sense Finding

The first return started Sense successfully, but its immediate read-only gate
ran before `dimos_he_sensors` had registered every Aurora ROS subscription.
The unchanged gate passed seconds later. This was a readiness race, not a
sensor, service, or safety failure.

The mode switch was updated to retry either complete gate at most six times,
five seconds apart. No individual check was relaxed. The fixed
`Sense -> shadow -> Sense` round trip passed: shadow admission passed, Sense
restoration passed within the bounded window, both services retained zero
restarts, and no RTAB-Map runner, odometry, map, or database-watchdog process
remained.

The short fixed round trip began after unrelated Git network activity had
raised system swap from 558MiB to 575MiB. During shadow startup it reached
619MiB, a runner-relative increase of about 44MiB, below the 64MiB health gate.
This does not replace the zero-growth ten-minute result and remains a longer-run
observation point.

## Final State

- Sense: enabled, active, zero restarts.
- Shadow: static, inactive, zero restarts.
- Deployment integrity and normal read-only gates: PASS.
- `/he/nav_cmd_vel`: zero publishers.
- `HEConnection.enabled=False`; LD19 remains retired.
- Native shadow process residue: none.

This closes static service isolation and bounded-switch qualification only.
Moving ATE/RPE, mapping quality, loop closure, displaced-start relocalization,
physical calibration, dynamic tracking, and real navigation remain prohibited.
