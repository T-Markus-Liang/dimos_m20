# HE Ackermann Platform

This package contains the DimOS adapters and deployment artifacts for the HE
Jetson Orin NX Ackermann platform.

## Safety State

- `HEConnection` is disabled by default.
- The persistent navigation topic has zero publishers until a later navigation
  phase explicitly passes its safety gates.
- Manual commands have priority over navigation through `twist_mux`.
- The final ROS controller applies 0.10m/s linear and 0.30rad/s angular limits,
  rejects non-finite commands, and stops/centers after a 100ms command timeout.
- No HE module publishes motor or steering PWM topics directly.

## Blueprints

- `he-sense-headless`: ROS sensor bridge plus bounded headless Rerun output.
- `he-teleop-headless`: sensor and movement wiring with real motion disabled.
- `he-nav-headless`: intentionally absent until trusted localization and the
  vehicle-down navigation gates pass.

## Sensors

`HESensorBridge` uses Aurora as the HE perception sensor and enables every
driver output by default:

- `color_image`: `/aurora/rgb/image_raw`, BGR8, limited to 5Hz;
- `depth_image`: `/aurora/depth/image_raw`, 16-bit depth, limited to 5Hz;
- `ir_image`: `/aurora/ir/image_raw`, 8-bit grayscale, limited to 5Hz;
- `pointcloud`: `/aurora/points2`, limited to 1Hz and stride-downsampled by 8;
- `camera_info`: `/aurora/rgb/camera_info`;
- `depth_camera_info`: `/aurora/ir/camera_info`, whose driver frame is
  `depth_camera_link` and supplies the depth/IR intrinsics;
- `imu` and command-integrated `odom` remain available for diagnostics.

LD19 is retired from the HE runtime and is not a bridge input. The Aurora
limits reduce DimOS and Rerun load; the ROS subscriptions remain active for all
modalities. Rerun keeps only the latest state in a 256MB recording window.

## Verification

Run the static closeout from the Orin repository root:

```bash
bash dimos/robot/he/deployment/verify-he-static-deployment.sh
```

The lifted real-command scripts require an explicit `--confirm-lifted` flag and
must not be run with the vehicle on the ground or without a physical stop path.

Run the bridge conversion tests with:

```bash
.venv/bin/python -m unittest -v \
  dimos.robot.he.test_connection dimos.robot.he.test_sensors \
  dimos.robot.he.test_visual_data
```

Collect a bounded SLAM-input diagnostic without enabling motion:

```bash
.venv/bin/python dimos/robot/he/deployment/diagnose-he-aurora.py \
  --samples 30 --timeout 15 --output /tmp/he-aurora-diagnostic.json
```

Preview or make a time-bounded raw dataset recording:

```bash
bash dimos/robot/he/deployment/record-he-visual-dataset.sh --dry-run
bash dimos/robot/he/deployment/record-he-visual-dataset.sh \
  --duration 10 --label static
```

Measure bounded stationary drift for a running shadow odometry topic:

```bash
.venv/bin/python dimos/robot/he/deployment/benchmark-he-visual-odom.py \
  --duration 60 --output /tmp/he-visual-odom-benchmark.json
```

See [Chassis characterization](docs/chassis-characterization-2026-07-11.md) for
the measured command-chain limits, latency, precision, and feedback gaps.

See [Aurora sensor rate reference](docs/aurora-sensor-rate-reference.md) before
changing camera/point-cloud rates or adding a full-rate perception pipeline.

The version-controlled deployment plan is
[Orin NX lightweight deployment](../../../docs/he/orin-nx-dimos-lightweight-deployment.md).
The visual SLAM evidence ledger and pilot order are in
[visual navigation candidate evaluation](../../../docs/he/visual-navigation-candidate-evaluation.md).
