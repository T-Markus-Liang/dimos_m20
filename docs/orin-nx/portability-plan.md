# WD Orin NX Portable Deployment Plan

Date: 2026-07-12 CST
Branch: `wd/orin_nx`
Base: upstream `feat/wd/m20` at `98713d97341bc9392e5dd531b1c13aaf98782a23`
Validated source: `codex/he-orin` at `f1b68218d9b32937f527c92ac2f9a14f5810a2e1`
Status: implementation active; Phase 1 complete, Phase 2/3 core adapters implemented

## 1. Objective

Build a reusable DimOS branch for NVIDIA Jetson Orin NX that preserves the
lightweight deployment, resource containment, safety, diagnostics and visual
shadow work proven on HE, while allowing each robot to provide different:

- RGB, depth, IR, point-cloud, lidar, IMU and odometry topics;
- sensor drivers and ROS setup overlays;
- differential, Ackermann, holonomic or no-motion control paths;
- ROS 2 Twist, CAN, serial, UDP or vendor-SDK chassis backends;
- transforms, frame IDs and calibration;
- service names, device aliases and resource budgets.

The branch must be deployable to a new Orin NX robot without renaming HE code or
editing hardcoded topics throughout the source.

## 2. Non-Goals

- Do not merge the complete `codex/he-orin` history or its large evidence files.
- Do not make Aurora 930, RTAB-Map or the HE Ackermann controller mandatory.
- Do not implement a universal hardware-driver plugin framework.
- Do not hide platform-specific safety limits behind generic defaults.
- Do not enable motion by default.
- Do not claim HE static/shadow evidence validates another robot platform.
- Do not carry the unrelated M20 `_m20_dan_rerun` fix into this branch unless it
  is separately required by the WD baseline.
- Do not install Nix, Cargo, simulation, GUI or agent dependencies on production
  Orin merely because they exist in the full repository.

## 3. Findings From The HE Delta

The HE branch contains four different kinds of work and they require different
migration treatment.

### 3.1 Generic and already validated

- daemon/coordinator idempotent shutdown;
- worker cleanup after daemon fork;
- nonblocking RPC cleanup;
- zombie-process detection;
- process-group ownership and bounded shutdown;
- Rerun latest-state display and bounded memory;
- systemd cgroup limits and fail-closed runtime gates;
- NVMe SMART/kernel startup admission;
- `PYTHONNOUSERSITE=1` isolation;
- bounded ROS image, CameraInfo, IMU, odometry and PointCloud2 conversion;
- command finite-value checks, clamp, timeout and repeated zero on shutdown;
- RTAB-Map child lifecycle, fresh database policy and size watchdog;
- localization-health and planner-map withholding;
- bounded diagnostics, fault injection and resource soak tooling.

These are candidates for extraction into the Orin NX common layer.

### 3.2 Generic algorithm with HE names/hardcoding

- `HESensorBridge`;
- `HEConnection`;
- `HEVisualSlamBridge`;
- `HELocalizationHealth`;
- `HEVisualMapAdapter`;
- `HERTABMapShadowRunner`;
- HE service-mode switching and read-only gates.

These should be renamed, parameterized and retested rather than copied as-is.

### 3.3 HE platform profile

- Aurora topics and driver service;
- Aurora point-cloud pre-throttle;
- Aurora SDK probes and depth A/B tooling;
- `/odom_raw` and `/ros_robot_controller/imu_raw`;
- `/he/nav_cmd_vel` and `/he/final_cmd_vel`;
- Ackermann limits, PWM behavior and controller patches;
- joystick/twist_mux priorities;
- HE camera transform;
- `/home/ubuntu/ros2_ws` and Aurora overlay paths;
- chassis lifted-test measurements.

These remain HE-specific reference material and must not become common defaults.

### 3.4 Evidence/archive only

- large health JSON captures and per-frame diagnostic output;
- Aurora vendor-support package inputs;
- NVMe incident and recovery reports;
- raw platform qualification results;
- RF2O and LD19 candidates;
- Codex session histories.

These stay on `codex/he-orin` and are linked from the migration record. Only
small design decisions and reusable threshold rationale should be summarized in
`wd/orin_nx`.

## 4. Proposed Architecture

Use four orthogonal layers with explicit ownership. The branch name identifies
the current productization target; it does not make Orin NX a robot type.

### 4.1 DimOS algorithm and transport layer

Planning, mapping, localization, control and visualization consume only DimOS
native streams. They do not import ROS, Aurora, HE or Orin-specific code. LCM
and Zenoh remain interchangeable transport backends selected by global config;
hardware adapters publish streams and do not select a transport themselves.

### 4.2 Hardware adaptation layer

Place reusable standard-protocol adapters under the existing hardware
ownership boundary:

```text
dimos/hardware/sensors/
  ros2_bridge.py
  test_ros2_bridge.py
dimos/hardware/drive_trains/
  ros2_twist.py
  test_ros2_twist.py
dimos/hardware/platforms/
  profile.py
  test_profile.py
  orin_nx/
    storage_health.py
    resource_health.py
    deployment/
    dimos-orin-storage-health.service
    dimos-orin-sense.service
    dimos-orin-shadow.service
    dimos-orin.env.example
    install.sh
    verify-storage.py
    verify-profile.py
    verify-readonly.py
    verify-static.py
    qualify-resource-soak.py
```

The ROS sensor adapter converts standard ROS messages to DimOS streams. The ROS
Twist adapter applies the common finite/clamp/watchdog/zero-stop contract. CAN,
serial, UDP and vendor SDK implementations are sibling robot-owned adapters;
they are not forced through ROS.

The Orin NX package owns only compute-target behavior: storage admission,
resource limits, headless services, process lifecycle and deployment gates.

### 4.3 Robot profile and composition

Use one validated JSON file per robot. JSON is selected because Python 3.10 can
parse it with the standard library and shell tooling can treat the path as an
opaque deployment input. No new dependency or config framework is needed.

Minimum profile surface:

```json
{
  "platform": "he",
  "ros": {
    "distro_setup": "/opt/ros/humble/setup.bash",
    "overlays": []
  },
  "sensors": {
    "odom": {"enabled": true, "topic": "/odom", "max_hz": 20},
    "imu": {"enabled": true, "topic": "/imu/data", "max_hz": 20},
    "color": {"enabled": true, "topic": "/camera/color/image_raw", "max_hz": 5},
    "depth": {"enabled": true, "topic": "/camera/depth/image_raw", "max_hz": 5},
    "ir": {"enabled": false, "topic": "", "max_hz": 0},
    "points": {"enabled": false, "topic": "", "max_hz": 0},
    "camera_info": {"enabled": true, "topic": "/camera/color/camera_info"}
  },
  "control": {
    "backend": "ros2_twist",
    "enabled": false,
    "topic": "/robot/nav_cmd_vel",
    "allow_lateral": false,
    "max_linear_mps": 0.1,
    "max_lateral_mps": 0.0,
    "max_angular_radps": 0.3,
    "rate_hz": 20,
    "timeout_s": 0.2
  },
  "runtime": {
    "rerun_memory": "128MB",
    "workers": 2,
    "memory_high_mb": 1024,
    "memory_max_mb": 1280
  }
}
```

The real schema will reject unknown fields, missing topics for enabled streams,
nonpositive rates, unsafe control defaults and duplicate output topics.

Profiles contain no passwords, Wi-Fi credentials, device serials or private
keys.

Profiles and robot-specific blueprints live with the robot:

```text
dimos/robot/he/
  profile.json
  blueprints.py
  deployment/
dimos/robot/<next_platform>/
  profile.json
  blueprints.py
  adapters/
  deployment/
```

HE is the first reference composition, not a superclass or a source of common
defaults. A second robot must be addable by supplying a profile and only the
adapters that its nonstandard protocols require.

### 4.4 Platform-specific adapters

A profile configures existing standard adapters. It does not pretend every
hardware protocol is ROS Twist.

- Standard ROS sensors use `ROS2SensorBridge`.
- Standard ROS velocity output uses `ROS2TwistConnection`.
- Direct CAN/serial/UDP/vendor SDK control remains a robot-owned DimOS module.
- A direct backend must still consume native DimOS `Twist` and implement the
  same finite/clamp/watchdog/zero-stop contract.
- Vendor driver services and udev rules live under the platform profile or a
  separate robot package, not in the Orin common layer.

No abstract base class is added initially. DimOS stream types already define
the data interface, and shared contract tests define the safety behavior. An
abstraction is promoted only after HE and a second platform demonstrate the
same requirement.

## 5. Common Module Contracts

### 5.1 Sensor bridge

The common ROS 2 bridge supports optional standard message channels:

- `sensor_msgs/Image`: color, depth and IR;
- `sensor_msgs/CameraInfo`;
- `sensor_msgs/PointCloud2`;
- `sensor_msgs/Imu`;
- `nav_msgs/Odometry`.

Required behavior:

- subscribe only to enabled channels;
- preserve source timestamp, frame ID, image stride and depth precision;
- rate-limit before conversion where practical;
- bound point-cloud rate and stride;
- publish small health metrics instead of duplicating full image payloads;
- use a single bounded executor thread unless measured evidence justifies more;
- stop executor/node/thread without residue;
- never require Aurora-specific fields.

A non-ROS sensor backend is a separate platform adapter that publishes the same
DimOS-native output streams.

### 5.2 Command bridge

The common ROS Twist backend retains the HE-proven fail-safe behavior:

- `enabled=false` by default;
- reject or zero NaN/Inf;
- independent linear, lateral and angular limits;
- lateral output disabled by default;
- stale-command watchdog;
- bounded publish rate;
- three spaced zero messages on shutdown;
- no publisher created when disabled;
- ROS output topic must not be a raw vendor motor/PWM topic.

Kinematics conversion and actuator feedback remain downstream platform
responsibilities. Ackermann steering PWM, differential wheel velocity and CAN
frames do not belong in the generic bridge.

### 5.3 Visualization

- headless by default;
- Rerun recording memory bounded by profile;
- latest-only entities for live sensor and health state;
- no GUI process on Orin;
- web viewer optional and separately enabled;
- point cloud disabled unless the profile explicitly enables it;
- no raw replay/history preload in the default live blueprint.

### 5.4 Storage and resource health

The generic storage gate keeps the proven policy:

- reject NVMe `critical_warning != 0`;
- reject `media_errors != 0`;
- reject current-boot critical medium, NVMe I/O, block update or EXT4 errors;
- report unsafe shutdowns without using them alone as rejection;
- run before sensor, shadow or control services.

Resource policy:

- systemd `MemoryHigh`/`MemoryMax`;
- bounded worker/task count;
- no automatic swap-growth acceptance;
- persistent soak output, never `/tmp`;
- no image/point-cloud payload retention in resource collectors;
- fail closed on service restarts, OOM events or motion publishers.

### 5.5 Visual SLAM

Visual SLAM is optional and disabled by default.

The common contract requires:

- synchronized RGB/depth/CameraInfo or another explicitly supported input set;
- platform-provided calibrated transforms;
- bounded database and process lifecycle;
- health output independent from planner output;
- planner map withheld unless health and map-quality gates pass;
- no `MovementManager` or command connection in shadow mode;
- mapping and localization modes separated;
- static evidence does not authorize moving navigation.

RTAB-Map remains the first reference backend, not a mandatory Orin component.

## 6. Deployment Model

Install into a configurable root rather than hardcoding
`/home/ubuntu/he/dimos_wd_m20`.

Proposed deployment variables:

```text
DIMOS_REPO=/opt/dimos
DIMOS_VENV=/opt/dimos/.venv
DIMOS_ORIN_PROFILE=/etc/dimos/orin-nx/profile.json
DIMOS_ROS_SETUP=/opt/ros/humble/setup.bash
DIMOS_ROS_OVERLAYS=
DIMOS_RUNTIME_USER=dimos
```

Systemd rules:

- generic units use an `EnvironmentFile`;
- storage admission is required before sensor/shadow services;
- platform driver units are separate dependencies;
- no `DISPLAY` or desktop session dependency;
- `PYTHONNOUSERSITE=1` on every Python/ROS service;
- motion/control unit not enabled by the installer;
- installer is idempotent and supports `--dry-run`;
- uninstall disables services but does not delete user data;
- service graph is validated with `systemd-analyze verify`.

The first implementation targets Ubuntu 22.04 / L4T R36.4.x / ROS Humble
because that is the validated HE ABI. Other JetPack/ROS combinations require a
new compatibility profile and explicit qualification.

## 7. Migration Plan

Implementation status as of 2026-07-13:

- Phase 0 and Phase 1 are complete and pushed.
- Phase 2 has the strict profile, HE reference profile and generic ROS 2
  sensor bridge; the sense blueprint and live ROS integration gate remain.
- Phase 3 has the fail-closed ROS 2 Twist bridge and software safety tests;
  backend contract documentation and the read-only graph gate remain.
- Phase 4 and later phases have not started.

### Phase 0: Baseline and provenance

Deliverables:

- keep `wd/orin_nx` rooted at `98713d97`;
- record source commit map from `codex/he-orin`;
- add this plan and branch-specific session log;
- define an allowlist of commits/files to migrate.

Gate:

- branch contains no HE runtime code yet;
- branch and origin HEAD match;
- WD baseline tests remain unchanged.

### Phase 1: Generic core lifecycle fixes

Review and port the proven core changes independently:

- idempotent coordinator stop;
- fork-safe worker waiting and SIGKILL fallback;
- nonblocking stop-RPC cleanup;
- zombie PID detection;
- daemon shutdown ordering.

Do not blindly cherry-pick the entire HE commit chain. Reapply minimal diffs
with their focused tests because later HE commits depend on platform runners.

Gate:

- existing coordination/CLI tests pass;
- new lifecycle tests pass on Python 3.10 and VM Python;
- no behavior change during normal blueprint startup.

### Phase 2: Profile and sensor template

Deliverables:

- strict robot `PlatformProfile` parser;
- example and HE reference profiles;
- generic optional ROS 2 sensor bridge;
- bounded headless sense blueprint;
- pure conversion and profile-validation tests.

Gate:

- unit tests cover BGR/RGB, mono8, mono16, row padding, endianness,
  CameraInfo, PointCloud2, IMU and odometry;
- disabled channels create no subscriptions;
- no hardcoded `/aurora`, `/he` or `/home/ubuntu` in hardware/common code;
- Rerun memory and latest-only surface are profile-derived and bounded.

### Phase 3: Command template and motion gate

Deliverables:

- generic ROS 2 Twist connection;
- backend contract documentation for direct CAN/serial/UDP adapters;
- software-only command safety tests;
- read-only graph gate.

Gate:

- output disabled by default;
- finite/clamp/lateral/watchdog/shutdown-zero tests pass;
- no publisher exists in sense/shadow modes;
- direct backend template cannot bypass final safety limits.

No physical motion test is part of generic branch acceptance.

### Phase 4: Portable systemd and installer

Deliverables:

- generic environment file;
- storage, sense and shadow units;
- idempotent installer;
- profile-aware integrity/read-only/static gates;
- persistent bounded soak collector.

Gate:

- no user/home path hardcoding;
- `systemd-analyze verify` passes;
- clean fixture passes storage gate and failed fixture is rejected;
- install dry-run makes no changes;
- motion services remain disabled.

### Phase 5: Optional visual shadow extraction

Deliverables:

- renamed visual bridge/health/map adapter;
- generic RTAB-Map runner configuration;
- database watchdog and child cleanup;
- planner-map withholding test.

Gate:

- all pure HE visual tests ported under generic names;
- map quality cannot be bypassed by profile values below hard safety floors;
- fault injection proves stale/malformed sensor data fails closed;
- shadow contains no command path.

### Phase 6: HE reference profile regression

Deliverables:

- HE JSON profile;
- HE-only Aurora service/drop-in examples;
- HE-only chassis notes/patch references;
- migration matrix pointing to original evidence, not copying large evidence.

Gate:

- generated common configuration reproduces validated HE topic/rate/resource
  values;
- HE unit tests that apply to common behavior pass;
- hardware-specific tests are marked `requires HE hardware` and are not counted
  as generic acceptance;
- no claim that a new HE deployment passed until replacement hardware exists.

### Phase 7: New-platform onboarding template

Deliverables:

- one-page platform questionnaire;
- example profile;
- driver/service checklist;
- sensor and control contract tests;
- acceptance evidence template.

Required onboarding inputs:

- Orin/L4T/ROS versions;
- sensor topic names, message types, rates, encodings and frame IDs;
- calibration and TF tree;
- chassis kinematics and command transport;
- feedback topics and units;
- physical speed/steering limits;
- watchdog/estop behavior;
- required vendor overlays and udev rules;
- network and bandwidth constraints;
- resource budget.

Gate:

- a second robot can be configured without editing common Python source;
- only its profile and adapter/service files differ;
- read-only and command dry-run gates pass before hardware motion.

## 8. Source Migration Matrix

| HE source | Planned destination | Treatment |
| --- | --- | --- |
| core shutdown commits | `dimos/core` | minimal port with tests |
| `HESensorBridge` | `hardware/sensors/ros2_bridge.py` | rename and parameterize |
| `HEConnection` | `hardware/drive_trains/ros2_twist.py` | rename, add optional lateral limit |
| storage health | `hardware/platforms/orin_nx/storage_health.py` | direct compute-platform extraction |
| memory/soak helpers | `hardware/platforms/orin_nx/resource_health.py` | compute-platform extraction |
| visual SLAM classes | navigation/mapping ownership after interface review | remove HE topics; do not place under Orin |
| HE blueprints | generic factories + HE profile | split |
| HE systemd units | generic templates + HE driver examples | rewrite |
| Aurora tools | HE reference profile only | do not make common |
| Ackermann patches | HE reference only | do not apply globally |
| large `docs/he/evidence` | link by commit/path | do not copy |
| NVMe incident docs | recovery rationale summary | do not treat as platform feature |
| M20 fix | none | exclude from Orin work |

## 9. Test Strategy

### Repository tests

- profile schema and invalid-config cases;
- message conversion;
- command safety;
- lifecycle and process cleanup;
- storage fixtures;
- resource summary;
- blueprint composition;
- generated registry;
- shell syntax and systemd unit validation.

### VM integration

- ROS imports with `PYTHONNOUSERSITE=1`;
- fake ROS topic publishers/subscribers;
- no-motion static closeout;
- process residue and bounded shutdown;
- installer dry-run.

### Orin static qualification

- storage admission;
- package/deployment integrity;
- sensor rates and timestamps;
- memory/CPU/GPU/temperature;
- latest-only visualization;
- command dry-run on isolated topic;
- shadow readiness and persistent soak.

### Robot-specific physical qualification

- command latency, deadband, min/max and precision;
- actuator feedback latency and accuracy;
- steering or angular response;
- watchdog and emergency stop;
- moving localization, loop closure and relocalization;
- controlled navigation.

Static Orin success never substitutes for physical robot qualification.

## 10. Completion Criteria

`wd/orin_nx` is ready for another robot only when:

- algorithm, hardware-common and Orin runtime code contain no HE/Aurora topic
  or absolute home path;
- one profile selects all standard sensors and resource limits;
- a non-ROS chassis can be added without changing common modules;
- storage and motion gates fail closed;
- sensor-only deployment is the default;
- core lifecycle tests and generic Orin tests pass;
- HE profile reproduces the validated configuration contract;
- a second profile passes VM/static gates;
- documentation clearly separates common proof from platform proof.

## 11. Risks And Controls

| Risk | Control |
| --- | --- |
| Over-generalizing from one robot | HE is a reference profile, not the common schema definition |
| Generic config bypasses safety | hard safety floors plus profile validation |
| Systemd/profile drift | deployment integrity hashes and generated effective-config report |
| ROS/Python package leakage | `PYTHONNOUSERSITE=1` and explicit overlays |
| Point-cloud memory/network overload | disabled by default, native throttle before conversion |
| Viewer recording growth | bounded memory and latest-only live entities |
| Driver process residue | process-group ownership and bounded stop |
| Storage regression | boot-time SMART/kernel gate |
| Unsupported JetPack ABI | compatibility matrix and explicit qualification |
| Hidden motion path | no command module in sense/shadow and graph-level publisher checks |

## 12. Recommended Decisions Before Implementation

The following defaults are recommended:

1. Use strict JSON robot profiles plus a small systemd environment file for
   deployment paths.
2. Keep ROS 2 standard messages as one reusable sensor/control adapter, not as
   a requirement for all hardware.
3. Keep direct CAN/serial/UDP drivers in robot-specific adapters.
4. Include HE under `dimos/robot/he` as a reference composition without
   copying large HE evidence.
5. Keep RTAB-Map optional and shadow-only by default.
6. Target L4T R36.4.x / ROS Humble first.
7. Merge generic core lifecycle fixes before platform modules.
8. Require a second profile before declaring the abstraction portable.

Implementation should start only after this plan is accepted or adjusted.
