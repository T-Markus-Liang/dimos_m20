# HE Orin NX Environment Inventory

Date: 2026-07-12 CST
Target observed: `ubuntu@192.168.1.106`
Repository branch: `codex/he-orin`
Target repository commit: `329c9c689422138be37b4257e33509db67a5d818`

## Purpose And Evidence Boundary

This is the replacement-storage reconstruction baseline for the HE platform. It
records system, runtime, hardware-interface and external-workspace dependencies
that are not fully described by the DimOS repository.

The audit used bounded read-only commands after the failed NVMe was powered on.
No package was installed, no filesystem repair was attempted and no sensor,
SLAM or DimOS workload was intentionally started. Passwords, keys, Wi-Fi
credentials, machine IDs, MAC addresses, disk serials and hardware serials are
excluded. Exact apt and Python versions are in
`docs/he/evidence/2026-07-12_orin-environment-packages.txt`.

## Immediate Safety Result

The NVMe failure is still active. This boot produced at least 935 matching
`critical medium error`/EXT4 error lines, including failures at sector 87084872.
SMART still reports 472 media errors and 32 unsafe shutdowns.

The old target commit predates `he-storage-health.service`. On boot:

- `he-camera-tf.service` was enabled and its `Wants=aurora930.service` pulled
  Aurora up even though Aurora itself was disabled;
- Aurora entered auto-restart and reached 84 observed restarts;
- joystick was also auto-restarting;
- twist mux and odom/motor controller were active.

The audit stopped and persistently disabled camera TF, Aurora, joystick, twist
mux and odom controller. Aurora, joystick, mux and odom also have runtime masks
for this boot. Sense and point-cloud throttle remain disabled; shadow remains
inactive. No related process remained at the final check. Runtime masks
disappear on reboot, so do not reboot the failed installation and assume it
remains protected.

## Hardware And Base OS

| Item | Observed value |
| --- | --- |
| Platform | NVIDIA Jetson Orin NX Engineering Reference Developer Kit Super |
| Device-tree identity | `p3768-0000+p3767-0000-super`, Tegra234 |
| Boot TNSPEC | `3767-300-0001-U.1-1-1-jetson-orin-nano-devkit-super` |
| Architecture | arm64 / aarch64 |
| CPU | 6 online Cortex-A78AE cores, 0-5, 115.2-1984MHz |
| RAM | 7.4GiB usable, 8GB class |
| Power profile | `MAXN_SUPER` |
| OS | Ubuntu 22.04.5 LTS, Jammy |
| Jetson Linux/L4T | R36.4.7, GCID 42132812 |
| Kernel | `5.15.148-tegra`, PREEMPT |
| Time zone | `Asia/Shanghai` |
| User shell | `/usr/bin/zsh`; ROS service commands must use Bash |

There is no installed `nvidia-jetpack` meta-package. Rebuild from the exact L4T
release/component versions, not from an unqualified JetPack 6 assumption.
`nvpmodel -q` reports MAXN_SUPER but warns about absent CPU6/CPU7 paths; that
warning is part of the observed six-core platform state.

## Storage Layout And Failure State

- Device: 128GB-class NVMe, 119.2GiB visible.
- Root: `/dev/nvme0n1p1`, ext4, 75.9GiB partition, approximately 49GiB used and
  22GiB available during the audit.
- EFI: `/dev/nvme0n1p10`, vfat, 64MiB.
- Root mount options: `rw,relatime`.
- Swap: zram devices plus `/swapfile`; about 13GiB total was reported.
- SMART: 40C, 99% available spare, 0% percentage used, 472 media errors,
  32 unsafe shutdowns and 175 power-on hours.

A zero critical-warning bit and 99% spare do not override direct unreadable
sectors. Do not clone this filesystem as a trusted system image. Flash a clean
compatible Jetson image to replacement storage and restore reviewed artifacts.

## NVIDIA Compute And Media Stack

| Component | Version/state |
| --- | --- |
| NVIDIA user driver | 540.4.0 |
| CUDA | 12.6; toolkit 12.6.11, nvcc/cudart 12.6.68 |
| cuDNN | 9.3.0.75 |
| TensorRT | 10.7.0.23, CUDA 12.6 build |
| VPI | 3.2.4 |
| NVIDIA container toolkit | 1.16.2; `nvidia-container` 6.2.1 |
| GStreamer tools | 1.20.3; L4T GStreamer 36.4.7 |
| Docker | 28.5.2; containerd 1.7.29 |

`/usr/local/cuda` resolves through alternatives to CUDA 12.6, but `nvcc` is not
on the login PATH. Use `/usr/local/cuda-12.6/bin/nvcc` or configure PATH
explicitly. Docker has an NVIDIA runtime entry but it is not the declared
default runtime. The current user cannot query the Docker daemon without
sudo/group access.

Three OpenCV layers coexist and must not be conflated:

- Ubuntu ROS/system libraries include OpenCV 4.5.4;
- NVIDIA/local deb packages provide OpenCV 4.8.0;
- the DimOS venv uses `opencv-contrib-python 4.13.0.92` with NumPy 2.2.6.

Preserve process isolation between ROS/Aurora and the DimOS venv. Do not add
global `LD_LIBRARY_PATH` entries that merge these ABI layers.

## Build Toolchain

- GCC/G++ 11.4.0
- CMake 3.28.3
- Ninja 1.10.1
- GNU Make 4.3
- Git 2.34.1
- colcon 0.20.1 package installed
- rosdep 0.26.0

Nix, Cargo, Rust, uv and git-lfs are absent. The installed DimOS environment
therefore depends on aarch64 wheels and already-built native artifacts; it is
not a complete on-device source-build environment. The default colcon/Python
startup is polluted by the broken user site and must run with
`PYTHONNOUSERSITE=1` or from a clean account/environment.

## ROS 2 And Localization Packages

- ROS distribution: Humble under `/opt/ros/humble`.
- Base: `ros-humble-ros-base 0.10.0`.
- Default RMW path: `rmw_fastrtps_cpp 6.2.9`; CycloneDDS 0.10.5 is installed,
  but no custom DDS config or active RMW override was found.
- RTAB-Map ROS: 0.23.7 for odom/slam/sync/util.
- twist_mux: 4.3.0.
- cv_bridge: 3.2.1.
- image_transport: 3.1.12.
- tf2_ros: 0.25.16.
- rosbag2: 0.15.15.

Required overlay order by workload:

1. Source `/opt/ros/humble/setup.bash`.
2. For Aurora, source
   `/home/ubuntu/third_party/aurora_ws/install/setup.bash`.
3. For the chassis controller, source
   `/home/ubuntu/ros2_ws/install/setup.bash`.
4. For DimOS, execute `.venv/bin/python` or `.venv/bin/dimos` directly with
   `PYTHONNOUSERSITE=1`.

Do not source ROS setup scripts from zsh. Existing service units correctly use
Bash.

## Python And DimOS Environment

- System Python: 3.10.12.
- DimOS venv: `/home/ubuntu/he/dimos_wd_m20/.venv`, Python 3.10.12,
  `include-system-site-packages=false`.
- Installed project: `dimos 0.0.13.post1`, source path at the HE repo.
- Viewer/Rerun: `dimos-viewer 0.32.0a1`, `rerun-sdk 0.32.0a1`.
- LCM: `dimos_lcm 0.1.3`, `lcm-dimos-fork 1.5.2.post1`.
- Numeric/geometry: NumPy 2.2.6, SciPy 1.15.3, Numba 0.66.0,
  Open3D unofficial arm 0.19.0.post9 and Pinocchio package 4.1.0.
- The venv contains 120 distributions; the exact list is in the snapshot.

The default system Python reads
`/home/ubuntu/.local/lib/python3.10/site-packages` and errors in
`distutils-precedence.pth`. ROS also failed earlier on unreadable `python_xlib`
metadata. Replacement services must keep `PYTHONNOUSERSITE=1`. Do not restore
the old user-site directory.

## Aurora 930 Stack

| Item | Observed value |
| --- | --- |
| USB identity | `3251:1930` |
| ROS driver source | `deptrum-ros-driver-aurora930-0.2.11` |
| Driver version macros | 0.2.11 |
| Deptrum stream SDK | Aurora900 SDK 1.1.22, aarch64 |
| Source commit | `c2bff34c634adf5c1998a00bb6914ca936b3b81b` |
| Workspace | `/home/ubuntu/third_party/aurora_ws`, about 125MiB |

The vendor workspace reports 67 modified files, almost all permission-mode
changes; the material diff is the package version line. Treat the verified
macOS backup as the restore source and compare content before rebuilding.

Launch defaults are RGB/IR/depth/point cloud enabled, RGB-D disabled, 15fps RGB
and IR, threshold 110, alignment and depth correction enabled, laser mode 1,
150-4000mm configured filter window and resolution mode 2. These are
configuration values, not a rated sensor-range or navigation-quality claim.

The camera is on the shared USB 2.0 480Mbps tree. The available USB 3.x root hub
reports 10Gbps with no child. Preserve this for the planned USB3 A/B.

## Chassis And Other Device Interfaces

- Chassis controller: USB `1a86:55d4`, CDC ACM, current node `/dev/ttyACM0`,
  intended stable alias `/dev/rrc`.
- Two CH340 adapters (`1a86:7523`) are visible, but no stable `/dev/ttyUSB*` node
  was present at audit time.
- Ring microphone: Rockchip `2207:0001` plus USB audio.
- Additional USB audio: `1b3f:2008`.
- CAN0 exists through `mttcan` with a 50MHz controller clock, but is DOWN and
  has no configured bitrate.
- Aurora and serial devices share a 480Mbps hub.

Current udev rules are evidence, not clean templates. They use broad `0666` or
`0777` permissions and the ttyACM rule appears to contain an extra trailing
character. Install reviewed least-privilege rules on the replacement system.
Hardware serial values are intentionally omitted from Git.

LD19 remains excluded from HE. Its legacy workspace/rule is not a required
replacement dependency.

## Network And Ports

- NetworkManager owns networking.
- Active path: Wi-Fi on `wlP1p1s0` with DHCP `192.168.1.106/24`.
- Gigabit Ethernet `enP8p1s0` exists but had no carrier.
- Jetson USB gadget bridge `l4tbr0` uses `192.168.55.1/24` when active.
- Docker bridge is `172.17.0.1/16`.
- CAN0, usb0 and usb1 were down.
- SSH listens on TCP 22. No DimOS/Rerun web ports remained after containment.

Wi-Fi SSID/credentials, MAC addresses and globally routable IPv6 addresses are
not stored in Git. Recreate NetworkManager credentials onsite.

## External Workspaces And Restore Policy

| Path | Purpose | Restore policy |
| --- | --- | --- |
| `/home/ubuntu/he/dimos_wd_m20` | HE DimOS, target at `329c9c68` | Clone current `codex/he-orin`; do not restore old checkout |
| `/home/ubuntu/third_party/aurora_ws` | Aurora driver/SDK overlay | Restore reviewed backup, then rebuild with ROS Humble |
| `/home/ubuntu/ros2_ws` | Vendor chassis/controller overlay, about 1.2GiB | Restore reviewed backup and reapply repository HE patches |
| `/home/ubuntu/he/ldlidar_ws` | Legacy LD19 | Do not restore for HE baseline |
| `/home/ubuntu/he/rf2o_ws` | Experimental lidar odometry | Do not restore as runtime dependency |
| `/home/ubuntu/he/data` and `logs` | Raw test data/logs | Keep in verified macOS backup; do not place in Git |

The old DimOS checkout is clean at `329c9c68`, but VM/GitHub remain canonical.
The legacy `large_models` source has uncommitted/generated content and is not
required for HE visual navigation.

## Systemd Reconstruction Rules

Install current repository units, not the old target copies:

1. Keep Aurora, camera TF, Sense, shadow, throttle, joystick, mux and odom
   disabled.
2. Install `he-storage-health.service` and current drop-ins.
3. Require `/run/he-storage-health.json` to report `healthy=true`.
4. Install reviewed udev rules and external ROS overlays.
5. Pass deployment integrity and read-only gates before enabling sensors.
6. Enable only the minimal sensor services required for qualification.
7. Keep joystick/motion disabled until separate safety authorization.

The old Aurora service lacks the storage dependency and user-site isolation
drop-in. The old camera-TF unit uses `Wants=aurora930.service`, explaining why
disabled Aurora restarted. Do not reproduce that graph.

## Replacement Acceptance Checklist

- Use a clean L4T R36.4.7-compatible flash.
- Require zero new-NVMe media errors and no current-boot storage errors.
- Reproduce the recorded CUDA/cuDNN/TensorRT/VPI and ROS ABI boundary.
- Rebuild Aurora 0.2.11/SDK 1.1.22 and review USB permissions.
- Restore the chassis overlay and pass repository patch integrity.
- Recreate DimOS from repository dependencies/aarch64 artifacts; do not copy
  the damaged venv or user site.
- Preserve `PYTHONNOUSERSITE=1` in ROS/Aurora and DimOS services.
- Pass storage, integrity, static-closeout, sensor and read-only gates in order.
- Rerun shadow admission and the interrupted two-hour persistent soak.
- Keep motion, moving localization and navigation separately gated.

## Backup Reference

Reviewed external artifacts remain under:

`/Users/markus/Downloads/he-orin-recovery-2026-07-12`

Its 1719 retained files and both HE rosbags were hash-verified. The generated
legacy speech grammar temporary directory was unreadable and excluded. This
inventory complements that backup; it does not authorize continued use of the
failed NVMe.
