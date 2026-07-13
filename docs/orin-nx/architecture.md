# WD Orin NX Architecture

Date: 2026-07-13
Branch: `wd/orin_nx`
Base: upstream `feat/wd/m20` at `98713d97`

## 1. Purpose

`wd/orin_nx` turns the HE deployment work into a reusable DimOS edge-runtime
baseline. HE is retained as the first measured robot profile, but it is not a
base class, common namespace or assumed hardware configuration.

The branch separates four concerns that were coupled in the original HE
prototype:

1. DimOS algorithms and transport.
2. Standard hardware protocol adapters.
3. Robot profile and robot-specific composition.
4. Orin NX compute deployment and resource admission.

This allows another Orin NX robot to change sensors, chassis protocol and
calibration without editing the common runtime.

## 2. Layered Design

```text
Robot drivers / vendor SDK / ROS 2 topics
                    |
                    v
dimos/hardware adapters
  ROS2SensorBridge / ROS2TwistConnection
                    |
                    v
DimOS-native streams and messages
                    |
          +---------+---------+
          |                   |
          v                   v
DimOS algorithms       Rerun visualization
mapping/navigation     bounded latest state
          |
          v
LCM or Zenoh runtime transport
```

### 2.1 Algorithm and transport layer

Mapping, localization, planning, control and visualization consume DimOS-native
messages. They do not import HE, Aurora or Orin deployment code.

LCM and Zenoh remain DimOS runtime transports. A hardware adapter publishes
normal DimOS streams; it does not choose LCM versus Zenoh. This keeps hardware
integration independent from deployment network topology.

### 2.2 Reusable hardware adapters

`dimos/hardware/sensors/ros2_bridge.py` converts standard ROS 2 Image,
CameraInfo, PointCloud2, Imu and Odometry messages. Every channel is optional,
rate bounded and disabled by default. Image row stride, endianness, source
timestamp and frame ID are preserved.

`dimos/hardware/drive_trains/ros2_twist.py` provides an optional standard ROS
Twist output. It is disabled by default and adds finite checks, linear/lateral/
angular limits, a stale-command watchdog and repeated zero commands on stop.

Direct CAN, serial, UDP and vendor SDK implementations do not belong in these
ROS adapters. They remain under `dimos/robot/<platform>/adapters` and must
implement the same command safety contract.

### 2.3 Robot profile and composition

`PlatformProfile` is the validated boundary between common code and robot
configuration. It owns:

- ROS setup and overlay paths;
- enabled sensor topics and maximum rates;
- point-cloud sampling;
- control backend and safety limits;
- worker count, Rerun memory and systemd memory budgets.

Unknown fields, relative enabled topics, duplicate topics, invalid rates,
unsafe lateral limits and inconsistent memory budgets are rejected.

`dimos/robot/he/profile.json` records the measured HE/Aurora configuration.
Future robots add their own `dimos/robot/<platform>/profile.json`. HE paths and
topics never become generic defaults.

### 2.4 Orin NX compute runtime

`dimos/hardware/platforms/orin_nx` owns compute-target behavior only:

- NVMe SMART and current-boot kernel storage admission;
- profile-driven systemd rendering;
- headless sense/shadow service lifecycle;
- cgroup memory limits and task bounds;
- ROS environment loading;
- dry-run and offline-root installation;
- motion-disabled startup admission.

The installer never enables or starts services.

## 3. Generic Sense Blueprint

`orin-sense-headless` is the common sensor-only entry point:

```text
ROS2SensorBridge(profile.sensor_config)
                |
                +--> DimOS Image / CameraInfo / PointCloud2
                +--> DimOS Imu / Odometry
                |
                v
RerunBridgeModule(
  rerun_open = none,
  memory_limit = profile.runtime.rerun_memory,
  latest_only_entities = sensor entities
)
```

It intentionally excludes:

- `ROS2TwistConnection`;
- `MovementManager`;
- planners, followers and motion controllers;
- click/teleoperation WebSocket input;
- simulation and desktop GUI processes.

The blueprint reads `DIMOS_PROFILE` at process startup. A repository-local
all-disabled profile exists only so static registry imports are deterministic.
Actual startup fails before deployment when `DIMOS_PROFILE` is absent, no
sensor is enabled, or motion is enabled.

## 4. Safety And Resource Flow

Systemd startup order is:

```text
dimos-orin-storage-health.service
                |
                v
profile validation (motion must be disabled)
                |
                v
dimos-orin-sense.service OR dimos-orin-shadow.service
```

The storage gate rejects NVMe critical warnings, media errors, spare below the
device threshold and current-boot kernel storage errors. Sense and shadow are
mutually exclusive and receive profile-derived `MemoryHigh` and `MemoryMax`.

Rerun is bounded by the profile and configured for latest sensor state. It is a
visualization consumer, not the sensor transport or recording authority.

## 5. Adding Another Orin NX Robot

1. Record JetPack/L4T, Ubuntu, ROS and Python compatibility.
2. Create `dimos/robot/<platform>/profile.json`.
3. Use standard ROS topics with `ROS2SensorBridge` where possible.
4. Add robot-owned adapters only for nonstandard protocols.
5. Add calibrated frame transforms and vendor driver services under the robot.
6. Run profile, conversion, storage and installer tests.
7. Render with installer `--dry-run`.
8. Start `orin-sense-headless` only after storage and read-only gates pass.
9. Qualify any future motion service separately; do not add it to sense/shadow.

## 6. Changes From WD M20 And HE

Compared with WD M20, this branch adds portable process shutdown, strict robot
profiles, generic ROS sensor/control adapters and an Orin deployment runtime.
It does not change M20 navigation algorithms.

Compared with the HE prototype:

- HE-named bridges are replaced by standard-protocol adapters;
- Aurora and Ackermann details stay in the HE robot layer;
- fixed `/home/ubuntu` paths are replaced by rendered deployment inputs;
- resource limits come from the profile;
- storage admission is compute-platform code;
- sense is a common read-only blueprint;
- motion and visual SLAM remain separate, explicitly qualified stages;
- large HE evidence is referenced by source commit rather than copied.

## 7. Current Boundary

Completed on this branch:

- portable lifecycle shutdown fixes;
- profile schema and HE reference profile;
- standard ROS sensor and Twist adapters;
- generic headless sense blueprint;
- storage admission and systemd installer.

Not claimed complete:

- a universal CAN/serial/vendor SDK interface;
- generic visual SLAM selection;
- moving navigation qualification;
- qualification of a second physical robot;
- deployment on the failed HE NVMe device.
