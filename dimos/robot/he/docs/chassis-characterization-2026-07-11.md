# HE Chassis Characterization - 2026-07-11

## Scope

The HE vehicle was lifted with its wheels clear. The test published short ROS
commands at 20Hz through the real command chain:

```text
/he/nav_cmd_vel -> twist_mux -> /he/final_cmd_vel
    -> odom_publisher -> motor RPS and steering PWM commands
```

The probe captured `/he/final_cmd_vel`, motor commands, steering PWM commands,
and `/odom_raw`. It first ran 83 characterization trials covering
forward/reverse speed, steering, explicit zero commands, command timeout, and
inputs above configured limits. A second focused suite ran 74 trials around
the software deadband, PWM quantization, steering saturation, and final command
limits.

This is command-chain characterization, not physical metrology. The platform
does not expose measured wheel speed or measured front-wheel angle. Therefore:

- RPS precision below means published motor-command precision.
- Steering precision below means PWM-command precision and nominal kinematics.
- Rise/fall latency ends at ROS actuator-command publication, not physical
  motor torque, wheel speed, or servo settling.

Raw evidence is stored on the Orin at
`/home/ubuntu/he/dimos_wd_m20/logs/he-chassis-characterization-20260711.json`.
Its SHA-256 is
`8a4ea0a5284077d621c71c28dd0f20a71d6a711f42c71e63107d2b00ec229a35`.
The focused command-limit evidence is
`/home/ubuntu/he/dimos_wd_m20/logs/he-chassis-command-limits-20260711.json`;
its SHA-256 is
`7a96c21fad3527022ca23aa238ee3049d1e8ae6bebd114c1bb9b0166331dc5fe`.

## Safety Finding Fixed Before Testing

The configured 0.10m/s and 0.30rad/s limits originally existed only in
`app_cmd_vel_callback`. The active `/he/final_cmd_vel` remap enters
`cmd_vel_callback`, so final limiting was not actually guaranteed.

The common callback now:

- clamps linear X and Y to +/-0.10m/s;
- clamps angular Z to +/-0.30rad/s;
- converts any NaN/Inf input tuple to a zero command;
- applies the same behavior to every command source before kinematics.

Inputs of +/-0.15m/s and +/-0.50rad/s confirmed the new final actuator limit.
The repository patch, ROS source, ROS build copy, and live process were checked
for consistency before characterization.

## Command Limits And Transfer

The Ackermann model uses:

- wheelbase: 0.17706m;
- track width: 0.17165m;
- wheel diameter: 0.085m;
- software steering limit: +/-34 degrees;
- center PWM: 1500;
- nominal PWM resolution: 0.09 degree per integer count.

Straight-line command transfer was exact at the ROS topic layer:

| Input speed (m/s) | Applied speed (m/s) | Motor 2 RPS | Motor 4 RPS |
| ---: | ---: | ---: | ---: |
| 0.001 | 0.001 | 0.003745 | -0.003745 |
| 0.003 | 0.003 | 0.011234 | -0.011234 |
| 0.005 | 0.005 | 0.018724 | -0.018724 |
| 0.010 | 0.010 | 0.037448 | -0.037448 |
| 0.030 | 0.030 | 0.112345 | -0.112345 |
| 0.050 | 0.050 | 0.187241 | -0.187241 |
| 0.080 | 0.080 | 0.299586 | -0.299586 |
| 0.100 | 0.100 | 0.374482 | -0.374482 |
| 0.150 | 0.100 (clamped) | 0.374482 | -0.374482 |

Reverse commands produced equal magnitudes with opposite signs. The smallest
tested command, 0.001m/s, produced a nonzero RPS command. This does not prove
that the physical motor overcomes friction at 0.001m/s; physical deadband still
requires encoder, tachometer, or external motion measurement.

### Focused Speed Command Boundaries

The second suite tested both signs immediately below, at, and above the
Ackermann software threshold, and immediately around the final safety clamp.

| Input magnitude (m/s) | Applied command state | Motor command |
| ---: | --- | --- |
| 0 to 0.000000009 | preserved in open-loop odom | zero |
| 0.000000010 | preserved | first nonzero RPS (`3.7448e-8` magnitude) |
| 0.099999 | preserved | proportional RPS |
| 0.100000 | preserved | maximum `0.3744822` RPS magnitude |
| 0.100001, 0.15, 0.50 | clamped to 0.100000 | same maximum RPS |

The positive and negative boundaries were identical. Therefore the measured
software executable speed-command range is `[-0.10, +0.10]m/s`, and the first
command that generates nonzero motor RPS is `+/-1e-8m/s`. Values below that
threshold are accepted by the ROS topic and appear in command-integrated odom,
but the Ackermann layer sends zero motor RPS. This tiny software threshold is
not a useful physical minimum: the smallest speed that actually turns the
wheels reliably is still unknown.

There is no acceleration or jerk ramp in this chain. New speed values are
translated to a motor command as a step. Any physical ramp inside the motor
controller is not exposed through ROS.

## Steering Transfer

The table uses 0.05m/s linear speed. Positive angular input is left steering.

| Absolute angular input (rad/s) | Applied angular (rad/s) | Nominal angle | Left PWM | Right PWM |
| ---: | ---: | ---: | ---: | ---: |
| 0.02 | 0.02 | 4.051 deg | 1454 | 1545 |
| 0.05 | 0.05 | 10.041 deg | 1388 | 1611 |
| 0.10 | 0.10 | 19.500 deg | 1283 | 1716 |
| 0.20 | 0.20 | 34.000 deg (limited) | 1122 | 1877 |
| 0.30 | 0.30 | 34.000 deg (limited) | 1122 | 1877 |
| 0.50 | 0.30 (clamped) | 34.000 deg (limited) | 1122 | 1877 |

The one-count left/right asymmetry comes from integer truncation in the PWM
conversion. Published PWM error against the current model was zero in all 83
trials. Actual steering angle, servo settling time, linkage ratio, backlash,
left/right mechanical symmetry, and load sensitivity remain unmeasured because
there is no steering-angle feedback.

Ackermann steering at zero linear speed is not supported by this path. A
zero-linear command results in zero motor command and centered steering rather
than steering in place.

### Focused Steering Command Boundaries

These measurements used `linear.x=0.05m/s`. Since the interface accepts yaw
rate rather than steering angle, the yaw-rate value at which the front steering
saturates changes with linear speed.

| Angular input | Left PWM | Right PWM | Result |
| ---: | ---: | ---: | --- |
| below `1e-8rad/s` | 1500 | 1500 | no steering PWM change |
| `1e-8rad/s` | 1499 | 1500 | first left count; right still centered |
| `0.00044rad/s` | 1499 | 1500 | right still centered |
| `0.00045rad/s` | 1498 | 1501 | first observed right count |
| `0.190rad/s` | 1122 | 1877 | PWM already at its integer saturation counts |
| `0.191rad/s` | 1122 | 1877 | geometric steering angle limited to 34 degrees |
| `0.300rad/s` | 1122 | 1877 | maximum accepted yaw-rate command |
| `0.300001` or `0.50rad/s` | 1122 | 1877 | clamped to `0.300rad/s` downstream |

The geometric 34-degree threshold at 0.05m/s is approximately
`0.19047456rad/s`. PWM integer conversion reaches the same observable endpoint
one count earlier. The first right PWM count is theoretically near
`0.00044358rad/s`, matching the 0.00044/0.00045 bracket.

The first-count left/right asymmetry is caused by Python `int()` truncating
values toward zero: any eligible tiny positive turn produces 1499, while a
tiny negative turn remains 1500 until it crosses a full count. The command
layer therefore has no symmetric steering deadband. This should eventually be
replaced by explicit rounding plus a calibrated physical deadband, but it was
not changed during characterization because no steering-angle sensor can prove
the correct calibration yet.

At zero linear speed, inputs of `+/-0.30rad/s` both produced zero motor RPS and
center PWM 1500. The software accepts yaw rate in `[-0.30, +0.30]rad/s`, but
the maximum front-steering command is PWM 1122 left and 1877 right, nominally
`+/-34 degrees`. No current evidence shows the physical wheels reach those
angles or respond to the one-count minimum.

## Latency

All values are measured with `time.monotonic()` in one probe process. `p95` is
the observed sample percentile, not a hard real-time guarantee.

### Command Up

| Stage | Samples | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Input publish -> `/he/final_cmd_vel` | 83 | 1.272ms | 2.139ms | 2.732ms |
| Input publish -> motor RPS command | 83 | 2.897ms | 4.014ms | 5.358ms |
| Input publish -> steering PWM (turning trials) | 36 | 3.802ms | 4.728ms | 6.521ms |
| Input publish -> `/odom_raw` command state | 83 | 13.877ms | 23.577ms | 24.501ms |

### Explicit Zero Down

| Stage | Samples | Median | p95 | Maximum |
| --- | ---: | ---: | ---: | ---: |
| Zero publish -> `/he/final_cmd_vel` zero | 78 | 1.316ms | 2.669ms | 3.545ms |
| Zero publish -> motor RPS zero | 78 | 2.959ms | 4.100ms | 4.919ms |
| Zero publish -> steering PWM 1500 | 78 | 3.668ms | 4.496ms | 6.094ms |
| Zero publish -> `/odom_raw` command zero | 78 | 14.453ms | 23.398ms | 24.788ms |

### Timeout Down

Five trials stopped refreshing the nonzero input without publishing zero:

| Stage | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: |
| Last input -> motor RPS zero | 112.772ms | 129.586ms | 150.913ms |
| Last input -> steering PWM 1500 | 114.021ms | 129.966ms | 152.198ms |
| Last input -> `/odom_raw` command zero | 123.676ms | 143.987ms | 157.595ms |

`twist_mux` becomes silent when its 100ms input timeout expires; it does not
publish an explicit zero on `/he/final_cmd_vel`. The independent 100ms odom
watchdog, checked on a 50ms timer, performs the observed motor stop and steering
recenter. This explains the approximately 100-150ms stop distribution and is
within the 200ms safety target.

## Precision Result

Across all 83 trials, maximum observed command-layer error was:

- motor RPS: 0.0;
- steering PWM: 0 counts;
- `/odom_raw` commanded linear speed: 0.0m/s;
- `/odom_raw` commanded angular speed: 0.0rad/s.

The 74 focused boundary trials also had zero RPS, PWM, and open-loop odom
command error. These exact results prove deterministic software conversion for
the tested inputs. They do not prove physical speed or steering accuracy.

## Remaining Physical Measurements

Before setting physical controller gains or claiming closed-loop accuracy,
measure:

1. wheel RPM versus requested RPS in both directions and at several battery voltages;
2. minimum speed that reliably starts and keeps rotating each driven wheel;
3. front-wheel angle versus PWM, including left/right asymmetry and hysteresis;
4. servo step settling time and overshoot under wheel load;
5. ground speed and yaw rate using visual SLAM or an external reference;
6. acceleration/deceleration behavior, since the current ROS chain has no ramp.

Until those measurements exist, `/odom_raw` remains command-integrated and the
platform does not have a physical velocity or steering feedback loop.

## Reproduction

Run only with the vehicle lifted and a physical stop path available. Stop the
joystick publisher so the script is the only navigation source:

```bash
source /opt/ros/humble/setup.bash
source /home/ubuntu/ros2_ws/install/setup.bash
cd /home/ubuntu/he/dimos_wd_m20
export VIRTUAL_ENV=$PWD/.venv
export PATH=$VIRTUAL_ENV/bin:$PATH
export PYTHONNOUSERSITE=1

sudo systemctl stop joystick-control.service
.venv/bin/python dimos/robot/he/deployment/characterize-he-chassis.py \
  --confirm-lifted --repeats 3 \
  --output-json logs/he-chassis-characterization-20260711.json

.venv/bin/python dimos/robot/he/deployment/characterize-he-chassis.py \
  --confirm-lifted --suite limits --repeats 1 \
  --output-json logs/he-chassis-command-limits-20260711.json
sudo systemctl start joystick-control.service
bash dimos/robot/he/deployment/verify-he-readonly.sh
```

The script sends five zero commands in its `finally` path. Operational wrappers
must also restore `joystick-control.service` with a shell trap if the test exits
early.
