# HE Visual Navigation Candidate Evaluation

Updated: 2026-07-11 14:00 CST

## Decision Status

This is the evidence ledger and test plan, not the final ADR. No candidate is
approved for navigation yet. The first hardware pilot is NVIDIA Isaac ROS
Visual SLAM in RGB-D mode because it has the strongest Orin/ROS 2 fit. RTAB-Map
RGB-D is the fallback and map-backend candidate. Selection remains gated by
Aurora depth, synchronization, HE recordings, Orin resource measurements and
repeatable trajectory results.

Real motion remains disconnected: `HEConnection.enabled=False`, LD19 stays
retired, and `/odom_raw` is excluded as SLAM truth.

## HE Constraints And Baseline

- Aurora provides one 640x400 RGB image, one depth image, one IR image and an
  organized 256,000-point cloud at about 13-15Hz. This is not a conventional
  calibrated stereo pair.
- The control-board IMU is about 47Hz. Camera-to-IMU extrinsics and clock
  alignment are not yet qualified.
- Live depth validity is only 17.6-20.4% globally in the samples seen so far.
  Spatial coverage and center ROI validity are a hard RGB-D admission gate.
- `he-dimos-sense` uses about 1006-1009MiB. The system currently has about
  3.5GiB available, but the completed stack must preserve at least 1GiB.
- Full-rate algorithm input stays local. The bounded latest-only Rerun path is
  not an algorithm input and remains independently rate-limited.

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
| Isaac ROS Visual SLAM / cuVSLAM | Official tree contains stereo, single-camera+IMU and RGB-D tests/launch. Publishes odometry/SLAM pose, status and pose graph; exposes reset, save/load map, set pose and localize-in-map services. | Main pushed 2026-07-07; Isaac ROS 4.4 update dated 2026-04-30; ROS 2 and Jetson/aarch64 are first-class. | Apache-2.0 wrapper; NVIDIA binary terms must be reviewed for deployment. | **First pilot.** Best Orin acceleration and health/map API fit. Aurora topic/calibration adaptation and RGB-D mode behavior must be proven. Do not assume RGB-D consumes the chassis IMU. |
| RTAB-Map + `rtabmap_ros` | RGB-D/stereo/3D lidar examples; RGB-D odometry, graph SLAM, loop closure, database persistence, point cloud and occupancy outputs. | Core pushed 2026-07-11; ROS 2 branch pushed 2026-06-25; ROS 2 Humble minimum and aarch64 binary evidence are documented. | BSD-3-Clause ROS package; audit linked libraries. | **Fallback / map candidate.** Strongest direct depth-to-navigation-map path and mature debugging. CPU/RAM/database growth on NX 8GB must be bounded. |
| ORB-SLAM3 | Mono, stereo, RGB-D; monocular/stereo visual-inertial; sparse map, multi-map and relocalization. | Official release v1.0 is from 2021; last source push 2024-07-24; official ROS example is ROS 1 Melodic/Ubuntu 18.04. | GPL-3.0. | Algorithmically relevant but engineering and license risk are high. The DimOS wrapper is incomplete and has a known transform defect. Keep as offline comparator only unless those are resolved. |
| OpenVINS | Mono/stereo + IMU MSCKF VIO, online camera/IMU spatial-temporal calibration, covariance and ROS 2 workflow. | Pushed 2025-11-30; official ROS 2 Ubuntu 22.04 Docker/build files exist. | GPL-3.0. | Lightweight VIO fallback when depth is unusable, but requires reliable camera/IMU timing and does not directly provide a navigation occupancy map or tightly coupled loop closure. |
| VINS-Fusion | Mono/stereo + IMU VIO and loop closure. | Last source push 2024-05-23; upstream integration is primarily older ROS/Ceres tooling. | GPL-3.0. | Lower priority than OpenVINS due maintenance/integration risk. Same synchronization and map-output gaps apply. |
| DPVO / DPV-SLAM | Learned monocular VO with optional DBoW2/classical loop closure; TartanAir, EuRoC, TUM-RGBD, ICL-NUIM and KITTI evaluation scripts. | Pushed 2024-10-12; tested Ubuntu 20/22 and CUDA 11/12; model/data download is about 2GB. | MIT code; verify checkpoint/data terms separately. | Useful offline learned comparator. Monocular scale, custom CUDA builds, model memory and lack of native ROS 2/occupancy output make it a poor first embedded baseline. |
| DROID-SLAM | Learned mono/stereo/RGB-D SLAM with trajectory and dense reconstruction. | Pushed 2025-05-05; current README states at least 11GB GPU memory for inference. | BSD-3-Clause code; verify weights. | Reject on Orin NX 8GB resource requirement. May run offline on a larger GPU for research only. |
| MASt3R-SLAM | Learned dense monocular SLAM and relocalization. | Official research implementation is active enough for evaluation but depends on large learned backbones and custom CUDA/PyTorch components. | Code and weights include research/non-commercial constraints that require a separate audit. | Offline research candidate only; resource and license risks prevent first deployment. |
| DINOv3 | Dense image features and image retrieval; no geometric pose estimator. | Meta repository pushed 2026-06-15; model card offers ViT and ConvNeXt sizes. | Custom DINOv3 license. | Never a standalone SLAM choice. Consider a small model later for place recognition/relocalization only after the geometric stack is stable. |

Official sources:

- https://github.com/NVIDIA-ISAAC-ROS/isaac_ros_visual_slam
- https://nvidia-isaac-ros.github.io/repositories_and_packages/isaac_ros_visual_slam/isaac_ros_visual_slam/index.html
- https://github.com/introlab/rtabmap
- https://github.com/introlab/rtabmap_ros/tree/ros2
- https://github.com/UZ-SLAMLab/ORB_SLAM3
- https://arxiv.org/abs/2007.11898
- https://github.com/rpng/open_vins
- https://docs.openvins.com/
- https://github.com/HKUST-Aerial-Robotics/VINS-Fusion
- https://github.com/princeton-vl/DPVO
- https://arxiv.org/abs/2408.01654
- https://github.com/princeton-vl/DROID-SLAM
- https://github.com/rmurai0610/MASt3R-SLAM
- https://github.com/facebookresearch/dinov3

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
3. Test Isaac ROS Visual SLAM RGB-D in an isolated ROS workspace. Record package
   version, launch configuration, pose/status/map services and resources.
4. Test official `rtabmap_ros` RGB-D odometry + mapping against the same bag.
5. Run OpenVINS only if camera/IMU timing passes and RGB-D tracking is not
   reliable. Run DPVO only offline as a learned comparator.
6. Produce the ADR only after repeatable HE trajectory and Orin measurements.
7. Integrate one selected runtime. A mapping backend may be paired with it, but
   multiple heavyweight SLAM frameworks must not remain resident on Orin.

Hard failures for selection are: unobservable metric scale, no tracking-health
signal, no navigation map path, incompatible license, less than 1GiB system
memory remaining, sustained swap, unbounded growth, or inability to recover
from a tested tracking loss.
