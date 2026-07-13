# Jetson Compatibility And Upstream Branch Assessment

Date: 2026-07-13
Target branch: `wd/orin_nx`

## Summary

The upstream Jetson work is useful as compatibility evidence, but none of the
reviewed branches is suitable for a wholesale merge.

- The WD M20 baseline already contains the later, generalized ARM dependency
  work, including `open3d-unofficial-arm` on Linux aarch64.
- The current Orin runtime architecture is newer and safer than the old Jetson
  Docker and humanoid integration layouts.
- Jetson ML wheels remain tied to the exact JetPack, CUDA and Python ABI.
  They must not be silently selected by the cross-platform lock.
- Sensor-only `orin-sense-headless` does not require Torch, ONNX Runtime or a
  local LLM. Add those only for a qualified algorithm that needs them.

## Reviewed Branches

| Branch | Head | Useful content | Decision |
| --- | --- | --- | --- |
| `jeff/jetson/1` | `0e4a7ec3` | Early JetPack 6.2 dependency experiment | Superseded by rebased branch; do not merge |
| `jeff/jetson/1-rebased` | `b7470dec` | aarch64 markers, Jetson AI Lab index, ARM Open3D choice | Concepts already partly upstreamed; document only |
| `jetson-humanoid-integration` | `791e9024` | Orin Nano 8GB setup notes and G1/ZED evidence | Branch is based on an old architecture; extract evidence only |
| `feature/mustafa-write-low-level-adapter-for-g1-humanoid` | `bda7ac5c` | Whole-body/G1 adapter patterns and CycloneDDS build lessons | Robot integration, not Jetson deployment |
| `andrew/feat/o3d-arm-cuda-support` | `482894d9` | NumPy `<2.4` cap for Numba compatibility | Current lock is already safe; leave dependency policy upstream |
| `matt-onnx-cuda-trt-mem-pin` | `b582a48e` | ONNX/TensorRT buffers and GPU memory pinning | Old vision architecture; future algorithm-specific reference |

The two named upstream repositories returned the same commit IDs for these
branches during this audit.

## Evidence Recovered From Upstream

`jetson-humanoid-integration` reports a tested environment:

- Jetson Orin Nano 8GB;
- JetPack 6.2;
- L4T 36.4.3;
- Ubuntu 22.04;
- CUDA 12.6.68;
- Python 3.10 wheels;
- cuSPARSELt for PyTorch builds that require it;
- G1 WebRTC command and ZED streaming integration.

This is historical integration evidence, not proof that every current DimOS
extra resolves on that platform.

## Current Qualified Runtime Matrix

The portable Orin runtime currently targets:

| Component | Qualified target |
| --- | --- |
| OS | Ubuntu 22.04 |
| Architecture | Linux aarch64 |
| L4T | 36.4.x |
| ROS | Humble when the selected robot profile uses ROS |
| Python core runtime | `>=3.10,<3.13` |
| Jetson ML wheel evidence | CPython 3.10 |
| CUDA evidence | 12.6 |
| Memory | 8GB-class minimum for the existing HE/Orin Nano evidence |

Python 3.11 or 3.12 may run the core DimOS package, but the reviewed Jetson GPU
repositories currently publish the relevant Torch and ONNX wheels primarily
for CPython 3.10. Do not infer GPU wheel compatibility from the core Python
range.

## Dependency State In This Branch

The current `pyproject.toml` already selects:

```text
Linux aarch64 -> open3d-unofficial-arm
other targets -> open3d
```

The generic `cuda` extra intentionally installs Cupy and ONNX Runtime GPU only
on x86_64. Running `uv sync --extra cuda` on Jetson therefore does not create
a qualified Jetson GPU environment.

The old `jetson-jp6-cuda126` extra remains disabled because hardcoded wheel
URLs and package versions became stale. On 2026-07-13:

- the Jetson AI Lab `jp6/cu126` index responded successfully;
- the reviewed ONNX Runtime 1.23 CPython 3.10 wheel responded successfully;
- the reviewed NVIDIA PyTorch 2.5 CPython 3.10 wheel supported a ranged fetch;
- the deprecated `pypi.jetson-ai-lab.dev` hostname did not respond;
- the live index had already moved to newer Torch/ONNX package versions.

Index availability is not an ABI guarantee. Pin exact URLs and hashes in a
robot deployment manifest only after testing them on the target JetPack image.

## Preflight

Run the read-only compatibility report before installing optional GPU
dependencies:

```bash
cd /opt/dimos
mkdir -p ~/dimos-evidence
.venv/bin/python -m dimos.hardware.platforms.orin_nx.compatibility \
  --output ~/dimos-evidence/jetson-compatibility.json
```

The report includes:

- architecture and Ubuntu version;
- Jetson model and L4T version;
- CUDA and Python versions;
- total shared memory;
- installed ARM Open3D, Torch, torchvision, ONNX Runtime GPU and xformers
  distribution versions;
- qualified-matrix errors and ML-wheel warnings.

`--strict` also returns nonzero for warnings. The tool is a preflight report,
not a systemd admission gate; storage health remains the mandatory gate.

## Deployment Tiers

### Tier 0: sensor and transport runtime

Use the smallest environment needed for:

- robot ROS/vendor drivers;
- `ROS2SensorBridge`;
- LCM/Zenoh transport;
- bounded Rerun output;
- `orin-sense-headless`.

Do not install Torch, ONNX Runtime GPU, xformers or local LLM dependencies
unless a selected Module imports them.

### Tier 1: GPU perception

For each algorithm:

1. record JetPack, L4T, CUDA and Python;
2. select exact aarch64 wheels and hashes;
3. install cuSPARSELt only when required by the selected PyTorch build;
4. verify imports and a CUDA tensor operation;
5. measure shared-memory and thermal behavior;
6. keep the wheel manifest robot/algorithm-specific.

### Tier 2: local language or vision-language models

Orin Nano/NX 8GB uses unified memory. Local models compete with sensor buffers,
maps, Rerun and the operating system. Quantization alone is not acceptance
evidence. Keep local LLM/VLM services optional, separately bounded and disabled
in the default sense deployment.

## Rejected Upstream Patterns

The following reviewed content is deliberately not copied:

- `docker/deprecated/jetson`: based on an old DimOS layout and broad,
  unpinned requirements;
- host-mounting all of `/usr/lib/aarch64-linux-gnu` into a generic Python
  container;
- an 8048MB container limit on an 8GB unified-memory target;
- `fix_jetson.sh`, which deletes and reinstalls system OpenBLAS libraries;
- `pip install --user` inside a virtual environment;
- automatic installation of rolling Jetson AI Lab packages;
- the complete old humanoid branch or ONNX/TensorRT vision stack.

## Integration Result

Integrated into `wd/orin_nx`:

- this current compatibility and branch assessment;
- a read-only compatibility report with fixture tests;
- corrected dependency comments and deployment documentation links.

Not integrated:

- upstream branch histories;
- stale wheel pins;
- deprecated containers or host library repair scripts;
- humanoid/G1 hardware modules;
- algorithm-specific ONNX/TensorRT changes.
