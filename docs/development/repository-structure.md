# Repository Structure

This document explains ownership boundaries in the DimOS repository and the
changes introduced by `wd/orin_nx` relative to its direct
`feat/wd/m20` baseline.

## Branch Lineage

```text
upstream/feat/wd/m20 (98713d97)
              |
              +-- wd/orin_nx
```

`feat/wd/m20` is the source baseline. `wd/orin_nx` preserves that baseline
and adds a reusable edge-compute runtime. It does not fork or replace the M20
navigation stack.

## Top-Level Map

```text
dimos/
├── dimos/          Python runtime, algorithms, hardware adapters and robots
├── native/         Rust native components
├── examples/       Small integration and language-interoperability examples
├── experimental/   Incubating work without stable compatibility guarantees
├── docs/           User, platform, capability and development documentation
├── data/           Runtime datasets and Git LFS pointers
├── assets/         Repository and README media
├── docker/         Container images and installation layers
├── scripts/        Installation, maintenance and developer entry points
├── bin/            Repository command wrappers
├── misc/           Auxiliary tools that do not belong to the runtime package
├── stubs/          Type stubs for external or generated interfaces
├── pyproject.toml  Python package, dependency and tool configuration
├── flake.nix       Nix development and deployment definition
└── uv.lock         Reproducible Python dependency lock
```

Generated build output, `.venv/`, caches and local recordings are not part of
this source layout.

## The `dimos/` Package

### Runtime and contracts

| Directory | Responsibility |
| --- | --- |
| `core/` | Module lifecycle, coordination, workers, daemon, RPC clients, global configuration and stream wiring |
| `protocol/` | Pub/sub, RPC, service and TF protocol implementations, including transport backends |
| `msgs/` | DimOS-native geometry, navigation, sensor, standard, TF and trajectory message types |
| `spec/` | Capability contracts used to connect implementations without importing robot-specific classes |
| `types/` | Shared domain value types and compatibility helpers |
| `porcelain/` | User-facing `dimos` CLI orchestration over the lower-level runtime |
| `codebase_checks/` | Repository-wide static architecture and convention checks |
| `e2e_tests/` | Cross-module and end-to-end runtime verification |

### Hardware and robot composition

| Directory | Responsibility |
| --- | --- |
| `hardware/` | Reusable device and standard-protocol adapters for sensors, drive trains, manipulators, whole-body systems and compute platforms |
| `robot/` | Robot-specific profiles, transforms, adapters and Blueprint composition |
| `simulation/` | Simulator-independent interfaces and MuJoCo, Genesis, Isaac and other engines |
| `teleop/` | Keyboard, phone, Quest and hosted operator input |
| `control/` | Generic coordinators, tasks and hardware-facing control composition |

The ownership distinction is important:

- Put a reusable ROS Image or Twist adapter in `dimos/hardware/`.
- Put Aurora setup, Ackermann PWM conversion or a vendor CAN frame in
  `dimos/robot/<platform>/`.
- Put the composition that selects those pieces in a robot Blueprint or a
  compute-platform Blueprint.

### Robotics capabilities

| Directory | Responsibility |
| --- | --- |
| `navigation/` | Global/local planning, path following, exploration, movement management and navigation stacks |
| `mapping/` | Occupancy, voxel, ray-tracing, costmap, loop-closure and map utilities |
| `perception/` | Detection, image embeddings, fiducials and scene registration |
| `manipulation/` | Manipulator planning, grasping, trajectory and servo control |
| `memory2/` | Spatial/temporal memory, storage, retrieval and visualization |
| `learning/` | Data collection and dataset preparation |
| `models/` | Shared model wrappers for embedding, segmentation and vision-language workloads |

### Agent, skills and presentation

| Directory | Responsibility |
| --- | --- |
| `agents/` | Agent runtime, capabilities, fixtures and agent-oriented demos |
| `skills/` | Callable robot and agent skills |
| `visualization/` | Rerun and generic visualization modules |
| `web/` | Web interfaces, templates and WebSocket visualization/control surfaces |
| `stream/` | Specialized audio/video stream helpers |
| `utils/` | Small cross-cutting helpers that do not own a domain |
| `experimental/` | Package-local prototypes not yet promoted to a stable owner |

## Dependency Direction

The intended dependency direction is:

```text
robot profile / Blueprint / deployment
                  |
                  v
hardware adapters and capability modules
                  |
                  v
native DimOS messages, specs and streams
                  |
                  v
core lifecycle and protocol backends
```

Lower layers must not import a robot profile. Algorithms consume DimOS-native
messages and should not depend on Aurora, HE, M20, Orin NX or a selected
transport. LCM and Zenoh are runtime transport choices, not hardware-driver
interfaces.

## Blueprints and Registration

A Module owns one behavior and declares typed `In[]` and `Out[]` streams. A
Blueprint configures and composes Modules. `autoconnect()` connects compatible
stream names and types; explicit remapping resolves intentional differences.

Runnable Blueprint variables are discovered into
`dimos/robot/all_blueprints.py`. That file is generated:

```bash
pytest dimos/robot/test_all_blueprints_generation.py
```

Do not edit the registry manually.

## Where New Code Belongs

| Change | Preferred location |
| --- | --- |
| New reusable sensor protocol | `dimos/hardware/sensors/` |
| New reusable chassis protocol | `dimos/hardware/drive_trains/` |
| Robot-specific CAN/serial/vendor SDK | `dimos/robot/<platform>/adapters/` |
| Robot topics, rates and limits | `dimos/robot/<platform>/profile.json` |
| Robot composition | `dimos/robot/<platform>/blueprints.py` |
| Compute admission or system service | `dimos/hardware/platforms/<compute>/` |
| Planner or path follower | `dimos/navigation/` |
| Mapping algorithm | `dimos/mapping/` |
| Standard message contract | `dimos/msgs/` or `dimos/spec/` |
| Native performance implementation | `native/` or a domain-owned native subdirectory |
| Incubating prototype | `experimental/`, followed by promotion to its final owner |

Tests normally live beside the code they verify.

## WD M20 Baseline

`feat/wd/m20` provides the complete DimOS repository plus the tested WD M20
navigation baseline. Its relevant platform code remains under:

```text
dimos/robot/deeprobotics/m20/
dimos/robot/m20/
dimos/robot/m20_native/
dimos/navigation/dannav/
```

The baseline already contains the general runtime, navigation, mapping,
simulation, visualization and LCM/Zenoh infrastructure. These remain available
to `wd/orin_nx`.

## Orin NX Evolution

`wd/orin_nx` adds four bounded areas on top of the WD baseline.

### 1. Portable lifecycle hardening

`dimos/core/` receives idempotent coordinator shutdown, fork-safe worker
waiting, zombie detection, daemon shutdown ordering and bounded asynchronous RPC
cleanup. These fixes are robot-independent.

### 2. Reusable hardware and profile boundary

```text
dimos/hardware/
├── drive_trains/ros2_twist.py
├── sensors/ros2_bridge.py
└── platforms/profile.py

dimos/robot/he/profile.json
```

Standard ROS 2 conversion is reusable. HE remains a reference robot profile,
not a parent package or source of generic defaults.

### 3. Orin NX compute runtime

```text
dimos/hardware/platforms/orin_nx/
├── blueprints.py
├── sense_profile.json
├── storage_health.py
└── deployment/
    ├── install.py
    ├── run-blueprint.sh
    └── *.service.in
```

This directory owns storage admission, profile-driven systemd rendering,
resource limits and the read-only `orin-sense-headless` entry point. It does
not own robot drivers or navigation algorithms.

### 4. Branch documentation

```text
docs/orin-nx/
├── architecture.md
└── portability-plan.md
```

These documents explain the compute/runtime architecture and migration
decisions. The current document explains the repository-wide source layout.

## What Orin NX Does Not Change

Relative to `feat/wd/m20`, the branch does not replace:

- M20 navigation, planning or tracking algorithms;
- mapping and perception implementations;
- simulation engines;
- LCM or Zenoh protocol semantics;
- the general Module and Blueprint programming model.

The result is an additive branch:

```text
WD M20 repository and tested navigation baseline
                     +
portable lifecycle, hardware adapters and profiles
                     +
fail-closed Orin NX headless deployment
```

For the detailed Orin runtime design, see
[WD Orin NX Architecture](../orin-nx/architecture.md).
