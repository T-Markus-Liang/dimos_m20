# Repository Structure Documentation

## Metadata

- Date: 2026-07-13
- Session id: current Codex desktop thread
- Project: dimos-orin-nx
- Workspace: VM `/home/markus/work/dimos_wd_m20`
- Task: document top-level repository responsibilities and compare wd/orin_nx with its feat/wd/m20 baseline
- Status: active
- Branch if relevant: `wd/orin_nx`

## User Request Summary

Add a concise repository layout overview to the root README and a detailed
directory-responsibility document. Compare only `wd/orin_nx` with its actual
`feat/wd/m20` baseline; do not include Ivan M20.

## Work Done

- Confirmed the worktree is clean and tracks `origin/wd/orin_nx`.
- Audited the Git-tracked top-level, `dimos/`, `native/` and `docs/`
  directory trees.
- Audited all changed files and eight commits from `feat/wd/m20` through the
  current Orin NX branch.
- Confirmed the Orin branch adds lifecycle hardening, common ROS adapters,
  profiles, Orin deployment and documentation without changing WD M20
  navigation algorithms.
- Added a concise `Repository Structure` section and navigation link to the
  root README.
- Added `docs/development/repository-structure.md` with top-level and Python
  package responsibilities, dependency direction, Blueprint registration,
  code-placement guidance, the WD baseline and the bounded Orin NX delta.
- Linked the existing Orin architecture document to the repository-wide guide.
- Verified all documented WD M20 paths exist in the baseline and that the Orin
  delta contains no navigation, mapping, perception or simulation changes.

## Decisions

- Keep the root README concise and link to one detailed development document.
- Use `feat/wd/m20` as the only baseline comparison.
- Describe tracked source layout, not local virtual environments, caches or
  generated build output.

## Current State

- Investigation is complete.
- Documentation is complete and ready for final diff verification and push.

## Resume Instructions

Read `README.md`, `docs/development/repository-structure.md` and
`docs/orin-nx/architecture.md`. Verify links and the baseline diff, then
commit and push documentation changes.

## Open Questions

- None.
