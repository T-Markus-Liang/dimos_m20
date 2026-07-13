# Upstream Jetson Branch Audit

## Metadata

- Date: 2026-07-13
- Session id: current Codex desktop thread
- Project: dimos-orin-nx
- Workspace: VM `/home/markus/work/dimos_wd_m20`
- Task: evaluate upstream Jetson and Orin Nano deployment work and integrate suitable content into wd/orin_nx
- Status: completed
- Branch if relevant: `wd/orin_nx`

## User Request Summary

Audit `jeff/jetson/1`, `jetson-humanoid-integration` and other upstream
branches for Orin/Jetson deployment documentation and implementation. Synthesize
the findings and integrate only content suitable for the portable
`wd/orin_nx` architecture.

## Work Done

- Confirmed the current worktree is clean.
- Queried official DimensionalOS, MeloLong upstream and the user fork for
  Jetson, Orin, Nano and humanoid branch names.
- Found and fetched `jeff/jetson/1`, `jeff/jetson/1-rebased`,
  `jetson-humanoid-integration` and the G1 low-level adapter candidate.
- Confirmed official and current upstream references point to the same branch
  commits.
- Audited each branch from its merge base, including commit history, changed
  files, Jetson docs, dependency markers, deprecated Docker artifacts and G1
  adapter work.
- Expanded the search to ARM/Open3D and ONNX/CUDA/TensorRT branches.
- Confirmed the WD baseline already contains the generalized ARM Open3D
  dependency support that originated from the Jetson experiments.
- Verified current upstream URLs: the `jp6/cu126` index, reviewed ONNX wheel
  and NVIDIA PyTorch ranged download responded; the deprecated `.dev`
  hostname did not. The live index package versions have moved.
- Added `docs/orin-nx/jetson-compatibility.md` with the branch matrix,
  qualified runtime matrix, dependency tiers, rejected patterns and integration
  decisions.
- Added a read-only compatibility report for architecture, Ubuntu, L4T, CUDA,
  Python, memory and installed Jetson ML distributions, with fixture tests.
- Updated the deployment and architecture docs and corrected the stale
  `pyproject.toml` comment without enabling rolling Jetson wheels.
- Verification: 40 focused tests pass, Ruff passes, `uv lock --check` passes,
  and the ARM VM correctly fails Jetson qualification because L4T is absent.

## Decisions

- Audit immutable remote refs without checking them out or disturbing the
  `wd/orin_nx` worktree.
- Classify findings before integration; do not cherry-pick a platform branch
  wholesale.
- Preserve the current split between compute runtime, reusable hardware
  adapters and robot-specific profiles.
- Do not merge or cherry-pick any candidate branch wholesale.
- Keep compatibility reporting separate from the mandatory systemd storage
  gate until a replacement physical Jetson is qualified.

## Current State

- Branch audit, selected integration and verification are complete.
- Implementation commit `41476166377f5f39b117e78fb61b4cfe4884cf11`
  is pushed to `origin/wd/orin_nx`.
- Local `HEAD` and `origin/wd/orin_nx` were verified equal after the push.

## Resume Instructions

No remaining work for this audit. For future Jetson deployment, read
`docs/orin-nx/jetson-compatibility.md`, run the compatibility preflight on the
target device, and store its output under `~/dimos-evidence/` before enabling
optional GPU dependencies.

## Open Questions

- None.
