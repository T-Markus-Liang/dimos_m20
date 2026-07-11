# Orin NX Car Hardware Audit

## Metadata

- Date: 2026-07-10 23:41 CST
- Session id: current Codex desktop thread
- Project: dimos-wd-m20
- Workspace: WD M20 baseline on VM plus deployment target `ubuntu@192.168.1.106`
- Task: inspect the Orin NX 8GB compute unit, mobile chassis, depth camera, single-line lidar, and their data interfaces
- Status: completed
- Branch if relevant: `feat/wd/m20`

## User Request Summary

Connect read-only to the Orin NX vehicle development kit and inventory compute resources, chassis interfaces, depth-camera interfaces, lidar interfaces, drivers, and live data paths for future DimOS deployment.

## Work Done

- Connected successfully over SSH without storing credentials in project files.
- Identified Ubuntu 22.04.5, Linux 5.15.148-tegra, L4T 36.4.7, aarch64, six Cortex-A78AE cores, and 7.4GiB RAM.
- Identified current `MAXN_SUPER` power mode, 13GiB swap, and root NVMe usage of 66GB/75GB (94%, 4.4GB free).
- Observed `nvpmodel -q` errors referencing nonexistent CPU6/CPU7 on the six-core device.
- Began network and device-interface inventory.
- Identified the platform as a front-steer, rear-drive Ackermann chassis using
  `MACHINE_TYPE=ROSOrin_Acker`.
- Mapped the chassis controller to `/dev/rrc -> /dev/ttyACM0` at 1,000,000
  baud and the LD19 lidar to `/dev/lidar -> /dev/ttyCH341USB0` at 230400
  baud.
- Identified Aurora 930 ROS 2 streams: RGB and depth at about 15Hz plus a
  PointCloud2 stream at about 14Hz and 58MB/s.
- Confirmed that the LD19 driver and udev rule exist but its node was not
  running, so no `/scan` topic was present.
- Confirmed that `/odom_raw` is command-integrated odometry, not measured
  wheel odometry.
- Identified two concurrent `ros_robot_controller` instances and a Wi-Fi
  button process opening the same `/dev/rrc` device.
- Identified that the camera TF tree is disconnected from the robot TF tree.

## Decisions

- Keep the audit read-only; no services, CAN configuration, or chassis commands
  were changed.
- Treat duplicate controller ownership, open-loop odometry, missing camera
  extrinsics, inactive lidar and disk pressure as deployment blockers.

## Current State

- Hardware and live interface inventory is complete enough to plan HE
  deployment. No hardware configuration has been changed.

## Resume Instructions

1. Read this completed audit, then read the active HE deployment-plan log.
2. Back up the specified hardware workspace and configuration before freeing
   disk space.
3. Resolve the P0 control ownership and TF issues before allowing any DimOS
   motion command.

## Open Questions

- Confirm the LD19 live scan topic and frame after its driver is started.
- Determine a trustworthy localization source before closed-loop navigation.
