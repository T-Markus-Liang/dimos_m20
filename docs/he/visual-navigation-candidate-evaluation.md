# HE Visual Navigation Candidate Evaluation

Updated: 2026-07-12 02:12 CST

## Decision Status

This is the evidence ledger and test plan, not the final ADR. No candidate is
approved for navigation yet. The first deployable pilot is RTAB-Map 0.23.7
RGB-D because an official ROS 2 Humble/Jammy arm64 package exists for the HE
baseline. Isaac ROS remains a future platform-upgrade candidate: the RGB-D
mode only appears in release 4.4+, whose apt repository is Noble/Jazzy, while
the compatible release 3.2 lacks RGB-D. Selection remains gated by Aurora
depth, synchronization, HE recordings, Orin resources and repeatable results.

Real motion remains disconnected: `HEConnection.enabled=False`, LD19 stays
retired, and `/odom_raw` is excluded as SLAM truth.

## HE Constraints And Baseline

- Aurora provides one 640x400 RGB image, one depth image, one IR image and an
  organized 256,000-point cloud at about 13-15Hz. This is not a conventional
  calibrated stereo pair.
- The control-board IMU is about 47Hz. A 598-second static run measured x gyro
  mean 0.03253rad/s (about 1.864deg/s) with only 0.000479rad/s span across nine
  60-second means. The driver applies correct deg/s-to-rad/s conversion but no
  calibration. Raw IMU fails VIO admission; camera-to-IMU extrinsics, clock,
  axes, temperature and six-position calibration are not yet qualified.
- Live depth validity is only 17.6-20.4% globally in the samples seen so far.
  Spatial coverage and center ROI validity are a hard RGB-D admission gate.
- The vendor SDK reports support range `0.3~1m` and no synchronized-two-image
  support. Existing live valid-depth p50/p95 is 1240/2522mm, so the range field
  is unresolved rather than used as a cutoff. RGB-depth remains software-paired
  and requires measured timestamp/quality evidence.
- `he-dimos-sense` uses about 1006-1009MiB. The system currently has about
  3.5GiB available, but the completed stack must preserve at least 1GiB.
- Full-rate algorithm input stays local. The bounded latest-only Rerun path is
  not an algorithm input and remains independently rate-limited.

The corrected 60-sample diagnostic on 2026-07-11 measured RGB 14.60Hz, depth
14.08Hz, IR 14.39Hz, point cloud 14.71Hz and IMU 47.22Hz. IMU-to-RGB nearest
offset was 5.81ms median and 10.29ms P95. Camera streams often shared exact
timestamps, but occasional one-frame gaps raised RGB-depth P95 to 68.35ms.
The driver was `align_mode=true`, `depth_correction=true`, but
`rgbd_enable=false`; driver documentation says RGB-D mode obtains RGB, depth,
IR and point cloud from one RGB-D frame. The isolated A/B did not improve image
pairing or depth validity and reduced point-cloud rate, so the default remains
off. This sensor is not treated as hardware-synchronized.

Depth was 20.51% valid globally and 15.76% in the center 40%. The latest lower
third tiles were only 4.93-5.72% valid, while upper corners were about 45%.
This is a spatial coverage failure for navigation until scene/mounting and
driver-mode tests explain it. Evidence is under `docs/he/evidence/`.

## DimOS Internal Audit

The refs below were fetched into isolated `research/*` refs. The HE worktree was
not switched or merged.

| Internal work | Ref / commit | Actual contract | Reuse decision |
| --- | --- | --- | --- |
| ORB-SLAM3 NativeModule | `research/orbslam3-native` / `a274e89d` | Python declares only `color_image`; outputs odometry, keypoints, sparse points and keyframe path. Config lists mono/stereo/RGB-D/IMU modes but those extra inputs are not represented in the Python port contract. | Do not merge. Reuse only interface ideas after checking the external C++ protocol. Its README explicitly records a trajectory transform mismatch. GPL-3.0 binary also needs product review. |
| RTAB-Map native backend | `research/rtabmap` / `e4610a9a` | Inputs registered point cloud, external odometry and optional RGB. Outputs corrected odometry, global map, octomap, projected grid and loop edges. | Useful map/loop-closure backend code, but it does not provide the missing Aurora visual odometry frontend as written. Port minimum map contracts only if the official ROS 2 RGB-D route cannot meet resource limits. |
| SLAM evaluation harness | `research/slam-bench` / `2c4d58e9` | Dataset loaders, ATE/RPE/timing and a generic DimOS module adapter; centered on odometry plus point-cloud backends. | Reuse metrics and dataset conventions. Extend for RGB/depth/IMU and HE rosbag inputs instead of copying the branch wholesale. |
| Point-cloud relocalization | `research/go2relocalization` / `9f710238`, `research/alfred-relocalization` / `12deee50` | ICP local cloud against a premap, fitness-gated world-to-map correction. | Possible later map-reuse fallback after a valid depth map exists; not a visual pose frontend. |
| PGO / loop closure | `research/go2loopclosure` / `22945ffb` | Pose-graph optimization, map reconstruction and recording components. | Candidate downstream component; inspect frame conventions before reuse. It cannot create metric visual odometry by itself. |
| ZED mapping experiment | `research/mapping-on-zed` / `134a0c51` | Commit itself states the ZED stereo-lidar route was not working. | Reject as implementation evidence. |
| Visual navigation sketch | `research/visnav` / `bd58527a` | Moondream/object-driven skill sketch. | Not SLAM or localization. |
| Semantic SLAM spec | `research/semantic-slam` / `a0ebf699` | Design proposal for semantic overlays; v1 excludes dense SLAM, loop closure and PGO. | Future semantic layer only. |
| Depth Anything 3 | `research/depth-anything3` / `9bf81685` | Monocular depth module. | Potential degraded-depth experiment, not pose, loop closure or localization. |

The internal RTAB-Map KITTI-360 loop detector recorded precision `0.6933`,
recall `0.1067`, F1 `0.1849`, maximum F1 `0.18538` and average precision
`0.07948` over a roughly 496-second run. These are loop-detection results for
that branch and dataset, not HE localization accuracy.

## External Maintained Candidates

Repository activity dates below are GitHub repository `pushed_at` values
observed on 2026-07-11. A recently pushed repository is not automatically a
better estimator.

| Candidate | Inputs / outputs | Platform and maintenance evidence | License | HE assessment |
| --- | --- | --- | --- | --- |
| Isaac ROS Visual SLAM / cuVSLAM | Release 4.4+ contains RGB-D tests/launch and map/status services. Release 3.2 supports stereo and single-camera+IMU but not RGB-D. | Latest v4.5-0 released 2026-07-07. Release-4 apt exists for Noble arm64 but not Jammy; current docs install ROS Jazzy packages. Compatible Jammy/Humble v3.2 has no RGB-D tree artifacts. | Apache-2.0 wrapper; NVIDIA binary terms must be reviewed. | **Deferred.** Strong Orin acceleration, but its usable RGB-D version is incompatible with the current OS/ROS baseline. Do not force an OS migration or pretend release 3.2 has the needed mode. |
| RTAB-Map + `rtabmap_ros` | RGB-D odometry, graph SLAM, loop closure, database persistence, cloud and occupancy outputs. | Core pushed 2026-07-11; ROS 2 pushed 2026-06-25. Orin apt offers 0.23.7 Jammy/Humble arm64 packages built 2026-06-22. | BSD-3-Clause ROS package; audit linked libraries. | **First pilot.** Strongest directly deployable depth-to-navigation-map path. CPU/RAM/database growth and poor depth coverage must be bounded and measured. |
| ORB-SLAM3 | Mono, stereo, RGB-D; monocular/stereo visual-inertial; sparse map, multi-map and relocalization. | Official release v1.0 is from 2021; last source push 2024-07-24; official ROS example is ROS 1 Melodic/Ubuntu 18.04. | GPL-3.0. | Algorithmically relevant but engineering and license risk are high. The DimOS wrapper is incomplete and has a known transform defect. Keep as offline comparator only unless those are resolved. |
| OpenVINS | Mono/stereo + IMU MSCKF VIO, online camera/IMU spatial-temporal calibration, covariance and ROS 2 workflow. | Pushed 2025-11-30; official ROS 2 Ubuntu 22.04 Docker/build files exist. | GPL-3.0. | Lightweight VIO fallback when depth is unusable, but requires reliable camera/IMU timing and does not directly provide a navigation occupancy map or tightly coupled loop closure. |
| VINS-Fusion | Mono/stereo + IMU VIO and loop closure. | Last source push 2024-05-23; upstream integration is primarily older ROS/Ceres tooling. | GPL-3.0. | Lower priority than OpenVINS due maintenance/integration risk. Same synchronization and map-output gaps apply. |
| DPVO / DPV-SLAM | Learned monocular VO with optional DBoW2/classical loop closure; TartanAir, EuRoC, TUM-RGBD, ICL-NUIM and KITTI evaluation scripts. | Pushed 2024-10-12; tested Ubuntu 20/22 and CUDA 11/12; model/data download is about 2GB. | MIT code; verify checkpoint/data terms separately. | Useful offline learned comparator. Monocular scale, custom CUDA builds, model memory and lack of native ROS 2/occupancy output make it a poor first embedded baseline. |
| DROID-SLAM | Learned mono/stereo/RGB-D SLAM with trajectory and dense reconstruction. | Pushed 2025-05-05; current README states at least 11GB GPU memory for inference. | BSD-3-Clause code; verify weights. | Reject on Orin NX 8GB resource requirement. May run offline on a larger GPU for research only. |
| MASt3R-SLAM | Learned dense monocular SLAM and relocalization. | Official research implementation is active enough for evaluation but depends on large learned backbones and custom CUDA/PyTorch components. | Code and weights include research/non-commercial constraints that require a separate audit. | Offline research candidate only; resource and license risks prevent first deployment. |
| DINOv3 | Dense image features and image retrieval; no geometric pose estimator. | Meta repository pushed 2026-06-15; model card offers ViT and ConvNeXt sizes. | Custom DINOv3 license. | Never a standalone SLAM choice. Consider a small model later for place recognition/relocalization only after the geometric stack is stable. |
| ScaRF-SLAM | Classical visual SLAM supplies poses; a geometric foundation model builds scale-consistent dense submaps. It is a mapping wrapper, not a replacement pose frontend. | Paper v1 published 2026-05-29. Official code was pushed 2026-07-07 and documents online/offline reconstruction. | GPL-3.0 plus third-party model terms. | Relevant future dense-map adapter after a trusted pose frontend exists. The foundation-model mapping path is too heavy and insufficiently qualified for the current NX 8GB runtime. |
| GeoGS-SLAM | Geometry-only Gaussian-splatting dense monocular SLAM with loop-corrected map updates. | Paper v1 published 2026-07-08. No official code or embedded deployment evidence was linked at audit time. | Not yet auditable. | Track only. A new paper without code, license, occupancy output or Orin evidence cannot enter the HE runtime baseline. |
| WildPose | Dynamic-aware monocular pose estimation using a frozen MASt3R backbone and differentiable BA. | Paper v1 published 2026-05-12. The paper links a project page but no official code repository was available at audit time. | Not yet auditable. | Offline research watch item for dynamic scenes. It lacks a navigation map contract and inherits a large foundation-model resource risk. |

Official sources:

- https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_visual_slam
- https://nvidia-isaac-ros.github.io/repositories_and_packages/isaac_ros_visual_slam/isaac_ros_visual_slam/index.html
- https://github.com/introlab/rtabmap
- https://github.com/introlab/rtabmap_ros/tree/ros2
- https://github.com/UZ-SLAMLab/ORB_SLAM3
- https://arxiv.org/abs/2007.11898
- https://github.com/rpng/open_vins
- https://docs.openvins.com/
- https://pgeneva.com/downloads/papers/Geneva2020ICRA.pdf
- https://github.com/HKUST-Aerial-Robotics/VINS-Fusion
- https://github.com/princeton-vl/DPVO
- https://arxiv.org/abs/2208.04726
- https://arxiv.org/abs/2408.01654
- https://github.com/princeton-vl/DROID-SLAM
- https://arxiv.org/abs/2108.10869
- https://github.com/rmurai0610/MASt3R-SLAM
- https://arxiv.org/abs/2412.12392
- https://github.com/facebookresearch/dinov3
- https://github.com/ori-drs/ScaRF-SLAM
- https://arxiv.org/abs/2607.07452
- https://arxiv.org/abs/2605.12774
- https://arxiv.org/abs/2605.03678

## Public Results: Scope Matters

- NVIDIA reports KITTI odometry runtime `0.007s`, translation error `0.94%`
  and rotation error `0.0019 deg/m` on Jetson AGX Xavier. This is vendor data
  on KITTI, not Aurora RGB-D or Orin NX 8GB evidence.
- The DimOS RTAB-Map figures above measure loop-detection precision/recall, not
  trajectory ATE/RPE.
- ORB-SLAM3, OpenVINS, DPVO and learned alternatives publish results on
  EuRoC/TUM/TartanAir/KITTI with different inputs and alignment rules. Their
  paper tables must remain separate from HE results; no cross-dataset score is
  used as a single ranking number.
- DROID-SLAM's own current 11GB inference requirement is direct exclusion
  evidence for the 8GB target regardless of its benchmark rank.

## Published Numeric Evidence

These tables preserve each paper's own input, dataset, alignment and hardware
scope. They are not combined into one score and are not HE acceptance results.

| Official source | Input and dataset | Reported result | Reported execution context | HE interpretation |
| --- | --- | --- | --- | --- |
| ORB-SLAM3 paper, Table II | EuRoC; mono, stereo, mono-inertial, stereo-inertial | Average RMS ATE `0.041`, `0.084`, `0.043`, `0.035m` respectively; monocular excludes one failed sequence | Intel i7-7700 3.6GHz, 32GB, CPU only. EuRoC V202 tracking averaged `21.52`, `31.48`, `23.22`, `33.05ms` for the four modes at 20Hz | Strong classical accuracy, but Aurora is not stereo and the HE DimOS wrapper is incomplete. GPL and old ROS integration remain deployment blockers. |
| OpenVINS paper, Tables II-III | EuRoC Vicon sequences; 20Hz camera and 200Hz IMU | Mono SLAM/VIO average ATE `0.079/0.148m`; stereo SLAM/VIO `0.054/0.055m`. Mono SLAM 8-48m translational RPE `0.074-0.122m` | Xeon E3-1505M v6 3.0GHz, single thread; mono SLAM/VIO `2.7x/4.3x` realtime and stereo `1.2x/1.9x` | Plausible lightweight VIO fallback, but HE's 47Hz IMU, unknown physical camera-IMU extrinsic and software timestamping do not match the paper setup. |
| DPVO paper | Monocular, scale-aligned; EuRoC/TartanAir/TUM-RGBD | EuRoC VO average ATE `0.105m`; TartanAir test average `0.21m`; TUM fr1 average `0.089m` | RTX 3090: default `60 FPS/4.9GB`, fast `120 FPS/2.5GB`; trained on synthetic TartanAir | Good offline comparator, but scale alignment hides the metric-scale problem and even the fast memory figure consumes a large fraction of unified NX memory. |
| DROID-SLAM paper | Monocular SLAM; EuRoC/TUM-RGBD/TartanAir | EuRoC average ATE `0.022m`; TUM fr1 average `0.038m`; TartanAir hard average `0.24m` | EuRoC `20 FPS` using two RTX 3090 GPUs; long sequences require a 24GB backend GPU. Current repository requires at least 11GB for inference | Accuracy does not overcome the direct NX 8GB memory exclusion. |
| DPV-SLAM paper, Tables 1-4 | Monocular SLAM; EuRoC/TUM-RGBD/KITTI/TartanAir | DPV-SLAM EuRoC `0.024m`, TUM `0.076m`; DPV-SLAM++ EuRoC `0.023m`, TUM `0.054m`. KITTI averages are much worse at `53.03/25.76m` | RTX 3090. DPV-SLAM: EuRoC `50 FPS/5GB`, TUM `30 FPS/4GB`; `++` adds about 2GB | Better bounded GPU use than DROID, but still no native ROS 2, metric scale, occupancy map or demonstrated aarch64 build. KITTI results show domain dependence. |
| MASt3R-SLAM paper | Monocular; TUM-RGBD/EuRoC/7-Scenes | Calibrated average ATE `0.030m` on TUM, `0.041m` on EuRoC and `0.047m` on 7-Scenes | All official experiments on RTX 4090; single-threaded average `14.6 FPS` across representative runs | The reported real-time claim is not Orin evidence. Large MASt3R checkpoints, custom CUDA and model licensing keep it offline-only. |

A May 2026 cross-system degradation study (`arXiv:2605.03678`) separately
reports Orin NX 15W latency of `8.4/29.4/68.3/95.0/142.5ms` for ORB-SLAM3,
DPVO, DROID-SLAM, DUSt3R and MASt3R, and reports DPVO at `3.1GB` GPU memory.
It also reports overall tracking success of `62.4/86.1/94.2/96.5/95.8%`.
This is a secondary UAV/custom-degradation study, not an official author
benchmark or Aurora test. Its numbers justify an optional DPVO Orin feasibility
probe only after the static safety work; they do not approve deployment.

## Unified HE Evaluation Matrix

Every runnable candidate receives the same artifact set:

| Area | Required evidence |
| --- | --- |
| Input | Exact Aurora topics, calibration, frame IDs, hardware/software synchronization, accepted missing-depth ratio and preprocessing. |
| Pose | Metric 6-DoF pose and trajectory; timestamp; covariance/quality; tracking-loss and recovery state. |
| Frames | One continuous dynamic `map -> odom -> base_footprint`; camera output transformed with measured extrinsics; no `/odom_raw` substitution. |
| Map | Sparse/dense representation, depth-derived obstacles, occupancy/traversability, save/load, loop closure and relocalization. |
| Accuracy | ATE RMSE, translational and rotational RPE, stationary drift, loop error, tracking coverage and relocalization success/time. |
| Robustness | Weak/repeated texture, lighting change, temporary occlusion, dynamic objects and missing depth. |
| Runtime | Input/output rate, p50/p95 latency, CPU/GPU/RAM/swap, temperature, dropped frames, service restarts and database/cache growth. |
| Engineering | ROS 2 Humble, aarch64/JetPack compatibility, install size/time, reproducible configuration and license/weight terms. |

## Pilot Order And Gates

1. Run `diagnose-he-aurora.py` and preserve its JSON. Resolve low center/spatial
   depth coverage, timestamps, intrinsics and camera-to-base/IMU extrinsics.
2. Record bounded raw HE datasets with `record-he-visual-dataset.sh`. Static
   recording is allowed now; motion datasets wait for a new vehicle-down
   safety confirmation.
3. Install only the minimal official RTAB-Map 0.23.7 odometry and SLAM packages,
   then test RGB-D odometry + mapping against the static bag and live shadow
   input. Record launch configuration, pose/status/map outputs and resources.
4. Keep Isaac ROS RGB-D deferred unless HE deliberately migrates to a supported
   Noble/Jazzy Jetson baseline; release 3.2 is not an equivalent RGB-D test.
5. Run OpenVINS only after the raw IMU bias/axis and camera/IMU spatial/time
   calibration gates pass, and only if RGB-D tracking is not reliable. Run DPVO
   only offline as a learned comparator.
6. Produce the ADR only after repeatable HE trajectory and Orin measurements.
7. Integrate one selected runtime. A mapping backend may be paired with it, but
   multiple heavyweight SLAM frameworks must not remain resident on Orin.

Hard failures for selection are: unobservable metric scale, no tracking-health
signal, no navigation map path, incompatible license, less than 1GiB system
memory remaining, sustained swap, unbounded growth, or inability to recover
from a tested tracking loss.

## First HE Pilot Result

RTAB-Map 0.23.7 passed the initial static feasibility gate. Tuned RGB-D odometry
ran for 60s with zero tracking losses, 0.48mm final/2.58mm maximum positional
drift, 0.051/0.102 degree rotational drift and 6.31Hz output. Median/P95 message
latency was 108/137ms. Odometry RSS peaked near 214MiB; adding the map process
used about 255MiB more in a short run. Occupancy, cloud, MapData, SLAM Info,
database persistence and the isolated dynamic TF chain were observed.

The static map benchmark then found only 2.52% known cells in an 82x59 map:
21 free and 101 occupied cells. This is an output-contract success but a
navigation-quality failure. The default HE health gate requires at least 10%
known space, so this result remains unhealthy and is withheld from planners.

ADR-001 selects RTAB-Map as the current shadow baseline, not as an approved
real-navigation stack. The static trajectory accumulated 0.236m of small
jitter, depth coverage is poor, and no moving/loop/relocalization data is
authorized yet. Full raw evidence is under
`docs/he/evidence/2026-07-11_1418_rtabmap-*` and
`docs/he/evidence/2026-07-11_1430_rtabmap-static-map.json`.

The integrated DimOS soak is recorded in
`docs/he/evidence/2026-07-11_1448_dimos-shadow-soak.md`. It confirmed bounded
runtime resources and fail-closed health, and it also found that blindly
resuming an incremental database after visual odometry resets can crash
RTAB-Map. The default runner starts a fresh bounded database. Explicit
`localization` mode now loads only an existing non-empty database with
incremental memory disabled, all saved nodes initialized and the database
opened read-only. Static same-scene reload and later moving/displaced-start
relocalization evidence must remain separate.

Static Orin evidence now confirms the read-only path loads a one-node database,
restores map correction, reports a good same-scene localization candidate and
re-emits the identical occupancy map without changing the database hash. This
is map-load feasibility, not a moving or displaced-start relocalization score.
See `evidence/2026-07-11_2237_static-map-reload.md`.

The integrated health gate has separate static fault evidence. A seven-second
Aurora outage added `pose_stale` in 0.459s and `tf_stale` in 1.032s, then
returned to the original baseline in 3.994s after service activation. This is
an input-freshness result, not a visual tracking-loss benchmark.

Fresh-content fault evidence extends that result. Blank RGB produced explicit
RTAB-Map `tracking_lost` and low-inlier status in 0.694s plus pose/TF freshness
failures, then recovered in 0.451s. Blank depth produced pose/TF freshness
failures without a new explicit lost status and recovered in 0.440s. These are
stationary synthetic content faults, not moving tracking or dynamic-object
benchmarks. See `evidence/2026-07-12_0041_fresh-visual-faults.md`.

An isolated RGB CameraInfo-only loss kept RGB/depth images fresh and withheld
42 calibration messages. Pose/TF freshness failed closed and recovered to the
baseline in 0.244s after CameraInfo resumed. It did not produce explicit lost
status. See `evidence/2026-07-12_0052_camera-info-fault.md`.

Direct calibration validation now adds explicit missing/invalid/stale reasons.
Zero-focal-length CameraInfo was rejected in 0.363s and valid calibration
restored the reason in 0.009s. See
`evidence/2026-07-12_0107_camera-info-health-gate.md`. A separate runtime
baseline-drift test kept images fresh while shifting focal lengths by 10% and
principal points by 10px. The bridge rejected the first fault state in 0.286s,
cleared it 0.135s after recovery and returned to the original map-quality-only
baseline in 0.510s. See
`evidence/2026-07-12_0118_intrinsic-baseline-drift.md`. This detects runtime
configuration drift; physical target calibration and extrinsics remain gates.
