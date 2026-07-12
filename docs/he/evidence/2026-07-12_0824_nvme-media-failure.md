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

Adding `PYTHONNOUSERSITE=1`, deleting the currently unreadable directory or
resetting service restart counters would only hide symptoms and is not an
accepted recovery.
