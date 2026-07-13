# README Runtime Diagrams

## Metadata

- Date: 2026-07-13
- Session id: current Codex desktop thread
- Project: dimos-orin-nx
- Workspace: VM `/home/markus/work/dimos_wd_m20`
- Task: improve the README repository overview with clear DimOS runtime and control-plane diagrams
- Status: completed
- Branch if relevant: `wd/orin_nx`

## User Request Summary

The existing one-to-two-level directory tree does not explain how DimOS works.
Improve the visualization and add whole-system runtime flow diagrams.

## Work Done

- Confirmed the branch is clean and the current README only provides a
  directory-first overview.
- Selected a runtime-first presentation with separate data/control and
  orchestration diagrams, followed by a source-layer map.
- Added a whole-system data-plane diagram covering sensors/replay, adapters,
  typed stream transport, perception, mapping/localization/memory,
  navigation/agents, bounded control, robot output and observability.
- Added a separate control-plane diagram covering CLI/systemd, configuration,
  Blueprint registry, ModuleCoordinator, requirement checks, workers, transport
  wiring and lifecycle handling.
- Added a source-layer table so readers can map diagram concepts back to
  directories before reading the detailed structure guide.
- Rendered both Mermaid diagrams with Mermaid CLI 11.16.0 and Chrome. The first
  draft was simplified after visual review to remove crossing publish-back
  arrows; both final diagrams render successfully.
- Committed and pushed as
  `423c71e0 docs(readme): visualize DimOS runtime architecture`. Local and
  remote heads matched at `423c71e027b71021d5050f63bf226f737bb25d48`.

## Decisions

- Use GitHub-native Mermaid so diagrams remain reviewable and maintainable as
  text without introducing binary assets.
- Keep data flow and control-plane orchestration separate to avoid implying that
  Coordinator processes sensor data.
- Preserve a concise directory tree and link to the detailed structure guide.

## Current State

- README diagrams are visually verified and pushed to `origin/wd/orin_nx`.

## Resume Instructions

Read the `Repository Structure` section in `README.md`, verify Mermaid syntax
and links, then commit and push.

## Open Questions

- None.
