# HE Aurora Git Baseline

## Metadata

- Date: 2026-07-11 12:40 CST
- Session id: current Codex desktop thread
- Project: dimos-wd-m20
- Workspace: VM `/home/markus/work/dimos_wd_m20`; runtime target `/home/ubuntu/he/dimos_wd_m20`
- Task: establish pushed Git version control, retire LD19 from HE, and make all Aurora sensor outputs default HESensorBridge inputs
- Status: completed
- Branch if relevant: `codex/he-orin` from `origin/feat/wd/m20`

## User Request Summary

Use Git commits and pushes for all subsequent HE changes with complete commit
messages. Retire the single-line LD19 from the HE platform and make every
Aurora output available through `HESensorBridge` by default.

## Work Done

- Confirmed the VM workspace is already a Git clone of
  `https://github.com/MeloLong/dimos.git` on `codex/he-orin`, but the branch has
  no upstream tracking and the accumulated HE work is uncommitted.
- Confirmed the established developer identity is
  `Markus.Liang <69946955+T-Markus-Liang@users.noreply.github.com>`.
- Configured the standard fork remotes: writable
  `origin=git@github.com:T-Markus-Liang/dimos_m20.git` and source
  `upstream=git@github.com:MeloLong/dimos.git`. The T-Markus-Liang account has
  no write access to MeloLong, so direct upstream push is intentionally avoided.
- Verified a dry-run push can create `origin/codex/he-orin`. Pushes use
  `GIT_LFS_SKIP_PUSH=1` because this is the intentional pointer-only clone and
  the upstream private LFS endpoint is not available.
- Audited the live Aurora node. It publishes RGB `bgr8`, depth `mono16`, IR
  `mono8`, PointCloud2, RGB CameraInfo and IR CameraInfo topics.
- Confirmed DimOS already provides native `Image`, `ImageFormat`, `CameraInfo`
  and `PointCloud2` types, so the bridge needs no new dependency.
- Committed and pushed the previously verified HE platform as baseline commit
  `fcfb09c6369427e88398ff0ed0e468d52b005b6d` with a complete commit message.
- Replaced the LD19-based bridge with six default Aurora inputs: BGR8 color,
  mono16 depth, mono8 IR, PointCloud2, RGB CameraInfo and IR/depth CameraInfo.
  The DimOS outputs use the standard names `color_image`, `depth_image`,
  `ir_image`, `pointcloud`, `camera_info` and `depth_camera_info`.
- Preserved native image precision and ROS timestamps/frames. Added row-padding,
  byte-order, CameraInfo matrix and ROI conversion, plus four standard-library
  unit tests. All ten HE tests pass on Orin.
- Retired LD19 from runtime and source deployment: disabled and removed the
  systemd unit, deleted the repository artifact, removed `/scan` and
  `/dev/lidar` gates, and removed the dependency from `he-dimos-sense`.
- Updated Rerun latest-only entities for every Aurora output while retaining
  the 256MB recording window. Default bridge limits are 5Hz for each image,
  1Hz for point cloud with stride 8, and 1Hz for each CameraInfo.
- Verified live ROS ingress: RGB/depth/IR about 15Hz, point cloud 256,000 points,
  both calibrations valid, and all six topics have exactly one Aurora publisher
  and one `dimos_he_sensors` subscriber.
- Verified live DimOS output with the LCM transport spy: RGB/depth/IR about
  4.4Hz, point cloud 1Hz, and both CameraInfo outputs 1Hz. Internal traffic was
  about 7.3MB/s, while a 10-second Wi-Fi sample was only about 18.6KB TX.
- Completed the canonical static closeout. Deployment integrity, ten tests,
  isolated control, Aurora quality and both read-only gates passed. Real motion
  remained disabled and `/he/nav_cmd_vel` had zero publishers.
- Observed `he-dimos-sense` plateau around 1008-1010MiB with `NRestarts=0`,
  below 1GiB MemoryHigh and 1.25GiB MemoryMax. VM and Orin HE trees match
  aggregate SHA-256 `6b924520...a6ab3ce`.
- Made the deployment plan version-controlled at
  `docs/he/orin-nx-dimos-lightweight-deployment.md`; the macOS Downloads copy is
  now a convenience mirror rather than the canonical source.
- Converted the Orin runtime checkout from `feat/wd/m20` plus copied files to a
  clean `codex/he-orin` checkout. Before changing HEAD, `git write-tree` exactly
  matched the remote implementation commit tree; afterward the worktree was
  clean and tracked `origin/codex/he-orin` at `968207d5...1aef`.
- Standardized VM and Orin remotes: personal fork as `origin`, public MeloLong
  repository as `upstream`. Final Orin deployment-integrity and read-only gates
  passed again with motion closed and about 1020MiB sensor cgroup memory.

## Decisions

- Preserve the already verified HE static deployment as a dedicated baseline
  commit before changing sensor architecture.
- Use a second focused commit for LD19 retirement and complete Aurora ingress.
- Keep Aurora streams local and bounded for Rerun; default ingress does not
  imply unbounded remote recording.
- Keep `HEConnection.enabled=False` and make no navigation/control change.
- Map `/aurora/ir/camera_info` to `depth_camera_info` because the driver publishes
  it in `depth_camera_link` and does not expose a separate depth calibration.
- Keep RGB/depth/IR at 5Hz and point cloud at 1Hz/stride 8 for the current viewer
  bridge. Visual SLAM may require a separate synchronized full-rate local path
  rather than raising the Rerun-facing rates.

## Current State

- Git governance, LD19 retirement and default Aurora ingress are complete.
- Real motion remains disabled; visual SLAM and navigation are still deferred.
- Aurora depth is connected but only 17.6-17.7% of pixels were nonzero in the
  current static view. Data availability does not yet imply RGB-D SLAM fitness.
- Sensor memory has limited headroom. Do not add a visual model to the same
  cgroup without first profiling and reducing the current footprint.

## Resume Instructions

1. Start from `origin/codex/he-orin` and read this log plus
   `docs/he/orin-nx-dimos-lightweight-deployment.md`.
2. Use complete commit messages and push every change with
   `GIT_LFS_SKIP_PUSH=1 git push`.
3. Investigate Aurora depth coverage, alignment and synchronization before
   selecting RGB-D/VIO algorithms.
4. Keep `HEConnection.enabled=False` until the later localization and
   vehicle-down safety gates pass.

## Open Questions

- Why does the static Aurora depth frame contain only about 17.6% nonzero
  pixels, with the center region previously observed empty?
- Does the driver provide hardware synchronization between RGB, depth, IR and
  IMU, or must the next phase add approximate synchronization and calibration?
