# HE Visual Benchmark And Extrinsics Audit

Date: 2026-07-11 15:39 CST

Scope: read-only public benchmark extraction and live HE frame audit. No motion
command, SLAM process or persistent configuration change was made.

## Public benchmark evidence

Official paper tables were inspected for ORB-SLAM3 (`arXiv:2007.11898`), DPVO
(`arXiv:2208.04726`), DROID-SLAM (`arXiv:2108.10869`), DPV-SLAM
(`arXiv:2408.01654`), MASt3R-SLAM (`arXiv:2412.12392`) and the OpenVINS ICRA
2020 paper linked by its official repository. The normalized results and
hardware boundaries are preserved in
`docs/he/visual-navigation-candidate-evaluation.md`.

The latest-paper scan also covered ScaRF-SLAM (`arXiv:2606.00307`), GeoGS-SLAM
(`arXiv:2607.07452`) and WildPose (`arXiv:2605.12774`). ScaRF-SLAM has GPL-3.0
code but is a learned dense-mapping wrapper around a classical pose frontend.
GeoGS-SLAM and WildPose had no auditable official code link at inspection time.
None currently supplies stronger HE deployment evidence than the bounded
RTAB-Map shadow baseline.

## Live frame evidence

The live static tree reported:

| Transform | Translation (m) | RPY (degrees) | Evidence class |
| --- | --- | --- | --- |
| `base_link -> camera_link0` | `[0.057373, 0.000079, 0.091864]` | `[0, 0, 0]` | HE Ackermann URDF nominal installation |
| `camera_link0 -> depth_camera_link` | `[0, 0, 0]` | `[-89.954, 0, -89.954]` | Generic platform axis convention, not measured mounting calibration |
| `depth_camera_link -> rgb_camera_link` | about `[-0.010, 0, 0]` | about `[-0.196, -0.044, -0.784]` | Aurora device calibration published by the driver |
| `base_link -> imu_link` | `[0.040, -0.015, 0.050]` | `[0, 0, 89.954]` | HE Ackermann URDF nominal installation |
| `imu_link -> depth_camera_link` | about `[0.015, -0.017, 0.042]` | about `[-89.954, 0, -179.909]` | Composition of the nominal URDF/service transforms |

Aurora CameraInfo remained `640x400`, `plumb_bob`, with RGB frame
`rgb_camera_link` and depth/IR frame `depth_camera_link`. The control-board IMU
published frame `imu_link`; its orientation quaternion was all zero, so the
message supplies raw angular velocity and acceleration rather than a valid
orientation estimate.

## Qualification result

- RGB-to-depth factory/device extrinsics are present and usable as driver
  calibration evidence.
- Camera-to-base and camera-to-IMU are only nominal frame-tree values. They
  have not been physically measured, target-calibrated or uncertainty-bounded.
- The `camera_link0 -> depth_camera_link` zero translation is especially not
  proof that the optical center is located at the URDF mounting origin.
- OpenVINS or any tightly coupled VIO remains inadmissible until physical
  camera-IMU spatial calibration, IMU axis/noise calibration and motion-based
  temporal calibration are completed.
- RTAB-Map may remain in shadow mode because its current qualification is an
  output/resource test; its pose and map must remain untrusted for navigation.

Safety state after the audit: `he-dimos-sense.service=active`, `NRestarts=0`,
no RTAB-Map/rgbd_odometry process remained, and `/he/nav_cmd_vel` had zero
publishers.
