# HE IMU Static Qualification

- Date: 2026-07-12 00:24 CST
- Orin commit: `90e283abb356a994e92cd7db69014a164e9ea565`
- Vehicle state: lifted and stationary; no motion command published
- Raw topic: `/ros_robot_controller/imu_raw`
- Temporary filtered topic: `/he/imu/orientation_probe`
- Filter: `imu_filter_madgwick` 2.1.5, gain 0.1, no magnetometer, no TF
- Duration: 30 seconds

## Results

| Metric | Raw | Madgwick filtered |
|---|---:|---:|
| samples | 1269 | 1394 |
| measured rate | 46.560Hz | 46.554Hz |
| median / P95 interval | 21.311 / 22.649ms | 21.312 / 22.683ms |
| nonpositive timestamp intervals | 0 | 0 |
| quaternion zero-norm samples | 1269/1269 | 0/1394 |
| quaternion norm median | 0 | 1.0 |
| final / maximum rotation from first | unavailable | 1.207 / 1.218deg |
| filtered RPY change | unavailable | +0.245 / +0.080 / -1.187deg |
| gyro mean x/y/z | 0.03327 / -0.00178 / -0.00177rad/s | same within noise |
| acceleration norm median | 9.9910m/s2 | 9.9910m/s2 |
| filtered orientation covariance all-zero | n/a | 1394/1394 |

The raw stream contains usable angular velocity and linear acceleration, but its
orientation is invalid. Madgwick creates a normalized orientation at the source
rate, but the stationary drift, gyro bias, all-zero orientation covariance and
unverified camera-to-IMU transform fail the HE admission gate. The current
RGB-D RTAB-Map shadow baseline remains unchanged; no IMU prior or tightly
coupled VIO is enabled.

The raw subscriber covered 27.23 seconds while the filtered subscriber covered
29.92 seconds in the same wall-clock run, despite nearly identical measured
rates. This is retained as an executor/DDS sampling caveat and is not used to
claim stream loss because the filtered node necessarily consumed the raw input.

## Cleanup And Safety

The `ros2 run` wrapper received SIGTERM; the native process was still visible
during the immediate post-stop race but was gone on the next bounded process
check. No probe topic or process remained. The live sensor gate and independent
read-only gate both passed afterward. `he-dimos-sense` and `aurora930` were
active with zero restarts, `/he/nav_cmd_vel` had zero publishers, and no visual
SLAM process was running.

Raw metrics: `docs/he/evidence/2026-07-12_0024_imu-qualification.json`.
