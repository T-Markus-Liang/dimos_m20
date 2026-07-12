# HE Orin NVMe Media Failure

Date: 2026-07-12 CST

Affected runtime commit: `329c9c689422138be37b4257e33509db67a5d818`

## Incident

The Orin lost network connectivity during a motion-disabled shadow soak and was
power-cycled onsite. The volatile soak report did not survive reboot. On the
next boot, `aurora930.service` entered a restart loop because ROS 2 could not
read Python package metadata from the root filesystem.

Kernel and NVMe evidence proved a storage failure rather than a camera or DimOS
failure:

- repeated `blk_update_request: critical medium error` reads;
- repeated EXT4 directory lookup errors on `nvme0n1p1`;
- direct `stat`, `head` and `sha256sum` returned `EIO` for affected files;
- NVMe SMART reported 472 media errors and 32 unsafe shutdowns;
- Aurora accumulated 22 failed restarts before it was stopped;
- additional unreadable files were found in a generated legacy speech grammar
  temporary directory during recovery copy.

`critical_warning=0` and 99% available spare do not override the direct media
errors and unreadable sectors.

## Containment And Backup

Aurora, HE Sense, point-cloud throttle and shadow services were stopped. No
navigation or motion process was active. The Orin was then shut down cleanly to
limit further root-filesystem writes.

The following were copied to macOS under
`/Users/markus/Downloads/he-orin-recovery-2026-07-12`:

- both HE visual rosbag datasets;
- HE runtime and qualification logs;
- Aurora and legacy ROS 2 source workspaces;
- systemd and udev configuration;
- NVMe SMART, dmesg and runtime-state diagnostics.

The recovery set is 1.2GB with 1719 retained files. Its top-level SHA-256
manifest verifies fully, and both HE rosbags independently pass their original
manifests. The unreadable generated speech grammar temporary directory is
explicitly excluded and documented in the recovery README.

The DimOS VM and GitHub copies remain the source-of-truth repository. Orin,
VM and GitHub were synchronized at `329c9c68` before shutdown.

## Recovery Gate

Do not resume shadow or sensor soak on this NVMe. Replace the storage device and
provision a fresh compatible Jetson baseline. Restore only reviewed artifacts,
then pass disk health, deployment integrity, Aurora, normal read-only and
shadow admission gates before restarting the two-hour soak. Filesystem repair
of the old device must be offline and preferably performed after a recovery
image; never run fsck against the mounted root filesystem.

`PYTHONNOUSERSITE=1` may isolate an unrelated user-package defect, but deleting
the unreadable directory, resetting restart counters or bypassing this storage
gate is not an accepted hardware recovery.

## Hardware Versus Dependency A/B

A second controlled boot separated the two failure layers:

- SMART still reported 472 media errors after reboot.
- Direct 512-byte reads of sectors 87084872 and 87057648 failed, while nearby
  sector 87084800 read successfully. The unreadable LBAs independently prove a
  physical media defect.
- ROS 2 with the default user site failed on the unreadable `python_xlib`
  metadata.
- ROS 2 with `PYTHONNOUSERSITE=1` returned successfully.
- A 15-second isolated Aurora launch with user site disabled opened the camera
  and began receiving frames.
- A transient systemd A/B then held Aurora active with RGB/depth at about
  14.72Hz. After one initial old-environment failure, no further restart
  occurred during the observation window.

Therefore both facts are true: user-site dependency leakage is a repairable
service configuration defect, and the NVMe has an independent physical media
failure. The Aurora drop-in now sets `PYTHONNOUSERSITE=1`, but the storage gate
still rejects this disk. Software isolation is not authorization to continue
deployment on damaged hardware.
