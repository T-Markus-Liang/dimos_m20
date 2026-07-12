# WD Orin NX Portability Planning

## Metadata

- Date: 2026-07-12 13:01 CST
- Session id: current Codex desktop thread
- Project: dimos-orin-nx
- Workspace: VM `/home/markus/work/dimos_wd_m20`
- Task: create `wd/orin_nx` from WD M20 and plan portable integration of validated HE lightweight deployment work
- Status: active - branch and planning complete; implementation awaits plan confirmation
- Branch if relevant: `wd/orin_nx` from `feat/wd/m20` at `98713d97`

## User Request Summary

Create a new Orin NX branch from WD M20, then plan how to integrate completed
and validated HE lightweight deployment work while turning sensors and chassis
communication into reusable templates for other Orin NX robot platforms.

## Work Done

- Verified the VM worktree was clean.
- Fetched upstream `feat/wd/m20` and confirmed local/upstream identity at
  `98713d97341bc9392e5dd531b1c13aaf98782a23`.
- Created `wd/orin_nx` from that commit, pushed it to
  `T-Markus-Liang/dimos_m20` and configured upstream tracking.
- Audited file, line and commit differences through HE head `f1b68218`.
- Separated generic lifecycle/resource/safety work from HE/Aurora/Ackermann
  platform code and large evidence.
- Inspected HE sensor, command, visual SLAM, systemd and verification hardcoding.
- Defined a three-layer architecture: Orin common runtime, strict platform
  profile and robot-specific adapter.
- Produced the phased migration, source matrix, validation gates, risks and
  completion criteria in `docs/orin-nx/portability-plan.md`.
- Verified the planning branch still contains no runtime/code changes and that
  documentation formatting and branch provenance are clean.

## Decisions

- Base the branch on upstream WD M20, not HE.
- Do not cherry-pick the complete HE history.
- Keep motion disabled and visual SLAM optional.
- Treat HE as the first reference profile, not as the common implementation.
- Use standard ROS messages for common adapters and leave direct hardware
  protocols in robot packages.

## Current State

- Branch exists locally and on origin.
- No HE runtime implementation has been merged.
- The only planned branch change is documentation/session state.
- Implementation is pending user review of the plan.

## Resume Instructions

Read `docs/orin-nx/portability-plan.md` and confirm or adjust the recommended
decisions in section 12. Then begin Phase 1 with minimal core lifecycle fixes and
focused tests.

## Open Questions

- Whether strict JSON is accepted as the platform profile format.
- Whether HE should ship as an in-tree reference profile or separate example.
- Whether the first second-platform target uses ROS Twist or a direct chassis
  protocol.
