# HE Orin Environment Audit

## Metadata

- Date: 2026-07-12 09:43 CST
- Session id: current Codex desktop thread
- Project: dimos-wd-m20
- Workspace: VM `/home/markus/work/dimos_wd_m20`; read-only target `ubuntu@192.168.1.106`
- Task: preserve all system dependency and environment information required to reproduce the HE Orin deployment
- Status: completed - environment inventory preserved; failed target safely powered off
- Branch if relevant: `codex/he-orin`

## User Request Summary

Inspect the powered-on Orin NX and record the system dependencies, runtime
versions, hardware/device interfaces, services and environment details needed
to reproduce the HE deployment after storage replacement.

## Work Done

- Confirmed the target is reachable at `192.168.1.106` after the user powered it on.
- Restricted the audit to bounded read-only commands; no package installation,
  filesystem repair, workload startup or broad disk scan is allowed.
- Confirmed the failed NVMe still emits current-boot critical-medium and EXT4
  errors at sector 87084872.
- Found `aurora930.service` unexpectedly activating despite being disabled and
  stopped it. It had accumulated 84 restarts. Sense, point-cloud throttle and
  shadow were inactive; no Aurora/RTAB-Map/DimOS process remained.
- Confirmed the old Orin deployment does not contain
  `he-storage-health.service`; that gate exists only in the newer VM/GitHub
  branch and must be installed before workloads on replacement storage.
- Captured the exact OS/L4T/kernel, CPU/RAM/power mode, storage layout, CUDA,
  cuDNN, TensorRT, VPI, ROS 2, RTAB-Map, build-tool and container versions.
- Captured all 120 DimOS venv distributions plus the rebuild-relevant apt
  package versions in a compact Git evidence file.
- Recorded Aurora driver/SDK identity, launch defaults, external ROS workspace
  locations, service dependency graph, USB/serial/CAN topology, udev risks,
  network interfaces and the reviewed restore boundary.
- Found the old camera-TF dependency repeatedly reactivating disabled Aurora;
  Aurora reached 84 observed restarts and the boot accumulated at least 935
  matching medium/EXT4 errors.
- Stopped and persistently disabled camera TF, Aurora, joystick, twist mux and
  odom controller. Added runtime masks for the current boot and verified all
  sensor, SLAM, DimOS and command processes were absent.
- Added `docs/he/orin-nx-environment-inventory-2026-07-12.md` and
  `docs/he/evidence/2026-07-12_orin-environment-packages.txt`, and linked the
  findings from the canonical lightweight deployment plan.
- Verified document paths, 120 captured venv distributions, relevant apt
  versions and repository formatting. Sensitive identifiers and credentials
  are excluded.
- Performed a final inactive/process-residue check, powered the Orin off
  normally and confirmed it was no longer network-reachable.

## Decisions

- Do not restart Aurora, DimOS, RTAB-Map or sensor workloads on the failed NVMe.
- Store the audit report and compact command evidence in VM/GitHub only.
- Exclude passwords, private keys, tokens, Wi-Fi credentials, serial numbers
  and unnecessary private user data from repository evidence.

## Current State

- Environment collection, documentation and verification are complete.
- Physical NVMe failure remains active and unrepaired.
- Aurora, camera TF, joystick, mux and odom are disabled/inactive; HE
  Sense/throttle/shadow are inactive and no related process remains.
- The Orin is powered off. VM/GitHub remain the canonical source of truth.

## Resume Instructions

Read the final environment inventory under `docs/he/`, then verify the current
service safety state before any future target access. Replace the NVMe, install
the current storage-health dependency graph and pass the documented recovery
gates before running workloads.

## Open Questions

- Whether to reproduce every package patch version exactly or accept newer
  compatible patches through controlled ABI/runtime A/B testing.
- Which replacement NVMe and clean Jetson image will be used for recovery.
