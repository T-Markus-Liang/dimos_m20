# HE IMU Ten-Minute Static Stability

- Date: 2026-07-12 01:33-01:43 CST
- Orin commit: `09efdd232`
- Vehicle: lifted and stationary
- Input: `/ros_robot_controller/imu_raw` only
- Motion state: `HEConnection.enabled=False`; `/he/nav_cmd_vel` publishers zero

## Driver Contract

The control-board firmware sends ax/ay/az/gx/gy/gz as six floats. The Python SDK
unpacks them without scaling. The ROS driver multiplies acceleration by standard
gravity and converts gyro degrees/second with `math.radians()`. It does not apply
bias, temperature, scale-factor or axis calibration and exposes no sensor model,
range or temperature. The observed gyro offset is therefore not a missing ROS
unit conversion, but its physical source cannot be separated in one pose.

## Capture Integrity

- 27,918 samples across 598.022 seconds of header time
- 46.682Hz mean rate
- 21.274ms median, 22.408ms P95 and 29.258ms maximum interval
- zero nonpositive timestamp intervals
- nine complete 60-second windows
- all 27,918 raw orientation quaternions remained zero-norm

## Static Results

| Metric | X | Y | Z |
| --- | ---: | ---: | ---: |
| gyro mean, rad/s | 0.032530 | -0.002002 | -0.001835 |
| gyro standard deviation, rad/s | 0.000997 | 0.000980 | 0.000731 |
| 60s window-mean span, rad/s | 0.000479 | 0.000283 | 0.000199 |
| stationary mean integral, deg | 1114.61 | -68.61 | -62.88 |
| acceleration mean, m/s2 | 0.3195 | 0.1060 | 9.9765 |
| acceleration standard deviation, m/s2 | 0.00182 | 0.00222 | 0.00332 |
| acceleration 60s window-mean span, m/s2 | 0.00153 | 0.00345 | 0.00567 |

Acceleration norm median was 9.9823m/s2. The x gyro mean is about 1.864deg/s;
it is much larger than its 60-second window variation and would integrate to
more than three full rotations over this capture if consumed without bias
handling.

Non-overlapping Allan deviation for gyro rate:

| Effective cluster | X rad/s | Y rad/s | Z rad/s |
| --- | ---: | ---: | ---: |
| 0.107s | 0.000426 | 0.000470 | 0.000396 |
| 1.007s | 0.000195 | 0.000179 | 0.000138 |
| 10.004s | 0.000189 | 0.000102 | 0.000071 |
| 60.001s | 0.000184 | 0.000095 | 0.000055 |

These bounded non-overlapping values describe this run; they are not a fitted
IEEE Allan-noise model and do not identify angle random walk or bias instability
coefficients from a single ten-minute record.

## Decision And Safety

Raw gyro must not be connected directly to RTAB-Map, OpenVINS or another VIO.
Do not persist the measured mean as a production correction: a six-position
calibration, axis verification, temperature characterization and physical
camera-to-IMU spatial/time calibration are still required. The RGB-D-only
RTAB-Map shadow baseline remains unchanged.

The diagnostic peaked near 100MiB RSS and about 10% of one CPU core. Available
memory stayed about 3.2-3.3GiB and the observed peak temperature was 63.4C.
After capture, the repository read-only gate passed, `he-dimos-sense` was active
with zero restarts, no localization process existed and navigation publishers
remained zero.

Raw evidence: `2026-07-12_0134_he-imu-static-10min.json` (SHA-256
`da38a37bc23f470714fa6a44cc10e702cd38ed8ffa335dfbfb0be4e84a8460ef`).
