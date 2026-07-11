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
- `he-visual-slam-shadow`: RTAB-Map, ROS-to-DimOS pose/map adapters,
  fail-closed localization health and bounded Rerun, with no motion modules.
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
  dimos.robot.he.test_visual_data dimos.robot.he.test_visual_slam
```

Collect a bounded SLAM-input diagnostic without enabling motion:

```bash
.venv/bin/python dimos/robot/he/deployment/diagnose-he-aurora.py \
  --samples 30 --timeout 15 --output /tmp/he-aurora-diagnostic.json
```

Query the vendor SDK's read-only support, temperature, laser-current and
factory camera-parameter getters under automatic service restoration:

```bash
sudo -v
bash dimos/robot/he/deployment/run-he-aurora-sdk-probe.sh \
  /tmp/he-aurora-sdk-probe.json
```

The runner briefly stops only the canonical Aurora service, never starts a
stream or calls an SDK setter, and reruns live-sensor and read-only gates after
restoration.

Measure raw IMU quality, or compare a temporary filtered orientation topic:

```bash
.venv/bin/python dimos/robot/he/deployment/diagnose-he-imu.py \
  --duration 30 --output /tmp/he-imu-raw.json
.venv/bin/python dimos/robot/he/deployment/diagnose-he-imu.py \
  --duration 30 --filtered-topic /he/imu/orientation_probe \
  --output /tmp/he-imu-filtered.json
.venv/bin/python dimos/robot/he/deployment/diagnose-he-imu.py \
  --duration 600 --output /tmp/he-imu-static-10min.json
```

The report includes 60-second block-mean stability, non-overlapping Allan
deviation at bounded cluster durations and the stationary gyro-mean integral.
These are diagnostics only: one stationary pose cannot identify accelerometer
bias, axis alignment, scale factor or temperature compensation.

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
.venv/bin/python dimos/robot/he/deployment/benchmark-he-visual-map.py \
  --duration 15 --output /tmp/he-visual-map-benchmark.json
.venv/bin/python dimos/robot/he/deployment/benchmark-he-localization-health.py \
  --duration 30 --output /tmp/he-localization-health.json
```

The localization-health benchmark is a read-only pLCM subscriber. It records
bounded samples, reason counts and every change in the `(healthy, reasons)`
state. Because poor map coverage is already an expected baseline reason, fault
tests must compare added and removed reasons instead of assuming the baseline
is healthy.

Run a bounded fresh-image fault proxy only with explicit isolated RTAB-Map
input overrides. It publishes no command and never writes to `/aurora/*`:

```bash
.venv/bin/python dimos/robot/he/deployment/inject-he-visual-fault.py \
  --mode blank-rgb --baseline 10 --fault-duration 8 --recovery 10 \
  --output /tmp/he-blank-rgb-fault.json
```

Use `--mode drop-camera-info` to keep RGB/depth images fresh while withholding
only the isolated RGB CameraInfo during the fault phase.
Use `--mode corrupt-camera-info` to keep publishing calibration messages with
zero RGB focal lengths and verify the explicit health validator.
Use `--mode shift-camera-intrinsics` to publish structurally valid K/P values
outside the approved HE runtime baseline tolerance.

The current RTAB-Map pilot can be checked or run without motion output:

```bash
bash dimos/robot/he/deployment/run-he-rtabmap-shadow.sh --check
bash dimos/robot/he/deployment/run-he-rtabmap-shadow.sh
```

Mapping always creates a new database. An explicit mapping path must not
already exist:

```bash
HE_RTABMAP_MODE=mapping \
HE_RTABMAP_DB=/var/tmp/he-rtabmap/he-map-new.db \
.venv/bin/dimos run he-visual-slam-shadow --daemon
```

Load an existing non-empty database in read-only localization mode with:

```bash
HE_RTABMAP_MODE=localization \
HE_RTABMAP_DB=/var/tmp/he-rtabmap/he-map.db \
.venv/bin/dimos run he-visual-slam-shadow --daemon
```

Localization forces non-incremental memory, initializes working memory from
the saved nodes, disables localization-data writes and opens the database
read-only. Loading a database does not prove relocalization quality; moving and
displaced-start tests remain gated by a new vehicle-down safety confirmation.

It publishes only `/he/visual_*` pose/map/status topics plus the isolated
`he_map -> he_visual_odom -> base_link` TF chain, and refuses to start if
`/he/nav_cmd_vel` has publishers. The integrated shadow stack can be started
with `dimos run he-visual-slam-shadow`; it remains unhealthy while the map
known-space ratio is below 10% and never includes a motion-output module.

See [Chassis characterization](docs/chassis-characterization-2026-07-11.md) for
the measured command-chain limits, latency, precision, and feedback gaps.

See [Aurora sensor rate reference](docs/aurora-sensor-rate-reference.md) before
changing camera/point-cloud rates or adding a full-rate perception pipeline.

The version-controlled deployment plan is
[Orin NX lightweight deployment](../../../docs/he/orin-nx-dimos-lightweight-deployment.md).
The visual SLAM evidence ledger and pilot order are in
[visual navigation candidate evaluation](../../../docs/he/visual-navigation-candidate-evaluation.md).
