# HE Orin NX Deployment And Visual Navigation Goal Status

Date: 2026-07-12 09:30 CST

## Source Of Truth

- Repository: `T-Markus-Liang/dimos_m20`
- Branch: `codex/he-orin`
- Canonical development copy: VM `/home/markus/work/dimos_wd_m20`
- Documentation baseline before this status update: `8a5855b676c51e6930265334a5138984a8caf8ce`
- Last commit deployed and synchronized to the Orin before the incident:
  `329c9c689422138be37b4257e33509db67a5d818`
- The Orin copy is intentionally behind the VM/GitHub branch. Do not synchronize
  or run workloads on the failed NVMe.

## Goal Status

`BLOCKED`: software work that can be completed without the target is preserved,
but the Goal cannot complete until the physical NVMe is replaced and the fresh
installation passes the storage admission gate.

The blocker is a confirmed physical media failure, not an unresolved DimOS,
Aurora or ROS dependency diagnosis. SMART retained 472 media errors and direct
reads of sectors 87084872 and 87057648 failed while a nearby sector succeeded.
An independent Python user-site leakage issue was reproduced and fixed with
`PYTHONNOUSERSITE=1` in the canonical Aurora service drop-in.

## Completed And Preserved In Git

- HE platform package, sensor bridge, bounded command adapter, Ackermann safety
  integration, headless blueprints and deployment artifacts.
- Lifted chassis command-path, watchdog, limits and steering PWM
  characterization. These are software/actuator-command results; physical
  wheel-speed and steering-angle metrology remains unproven.
- Aurora RGB, depth, IR, point-cloud and IMU integration, diagnostics and
  bounded visualization behavior.
- RTAB-Map RGB-D shadow baseline, lifecycle ownership, health reporting,
  planner-map withholding, resource limits and fault tests.
- Static deployment, read-only, sensor, control dry-run, integrity, shadow
  admission and bounded soak tooling.
- 93 derived evidence files under `docs/he/evidence`, including the NVMe
  failure report and the last valid static qualification results.
- Fail-closed NVMe startup admission and Aurora user-site isolation for the
  replacement installation.

## Incomplete Or Invalidated

- The formal two-hour shadow soak was interrupted by the storage failure. Its
  volatile partial output was lost and is not accepted as evidence.
- Replacement-storage startup admission has only fixture/VM validation; it has
  not passed on new Orin hardware.
- Visual map quality remains below planner admission, Aurora bottom depth
  coverage remains unhealthy, and `/global_costmap` remains withheld.
- Physical camera-to-base and camera-to-IMU calibration, moving localization,
  loop closure, relocalization, navigation and exploration remain open.
- No field-motion authorization follows from lifted command tests or static
  shadow tests.

## Git And External Backup Boundary

Git contains source code, configuration, tests, documentation and compact
derived evidence. Large/raw artifacts are deliberately outside Git.

The verified recovery package is:

`/Users/markus/Downloads/he-orin-recovery-2026-07-12`

It contains 1.2GB and 1719 retained files: two HE rosbags, HE logs, Aurora/ROS
source, systemd/udev configuration and disk diagnostics. The top-level SHA-256
manifest and both original rosbag manifests pass. Unreadable generated legacy
speech grammar temporary files are explicitly excluded in its README.

## Current Safety State

- The affected Orin is powered off.
- `aurora930.service`, `he-dimos-sense.service` and
  `he-pointcloud-throttle.service` were persistently disabled before shutdown.
- Shadow is inactive; no Aurora, RTAB-Map or navigation process remains.
- No motion or navigation command was active during the incident.

## Recovery Sequence

1. Replace the failed NVMe and provision a compatible clean Jetson system.
2. Clone `codex/he-orin` from GitHub. Do not treat the old Orin checkout as the
   canonical repository.
3. Restore only reviewed hardware/ROS artifacts from the macOS recovery set.
4. Install the repository storage-health unit and service dependencies before
   enabling Aurora or HE workloads.
5. Require `/run/he-storage-health.json` to report `healthy=true` on the new
   storage.
6. Pass deployment integrity, Aurora live sensor, HE static closeout and final
   read-only gates with navigation publishers at zero.
7. Pass shadow admission and rerun the formal two-hour soak to persistent
   storage.
8. Only after those gates pass, plan physical calibration and controlled
   moving localization/navigation qualification.

## Resume Condition

Resume this Goal only after replacement NVMe installation and a successful
storage admission report. Until then, VM/GitHub are the canonical HE branch and
the powered-off Orin must remain unsynchronized.
