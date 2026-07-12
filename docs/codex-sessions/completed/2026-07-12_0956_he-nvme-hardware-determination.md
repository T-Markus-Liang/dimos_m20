# HE NVMe Hardware Failure Determination

## Metadata

- Date: 2026-07-12 09:56 CST
- Session id: current Codex desktop thread
- Project: dimos-wd-m20
- Workspace: VM `/home/markus/work/dimos_wd_m20`; verified macOS recovery evidence
- Task: formalize the method and conclusion proving the Orin NVMe hardware failure
- Status: completed - formal determination and approved wording recorded
- Branch if relevant: `codex/he-orin`

## User Request Summary

Produce a fixed, defensible record of how the NVMe hardware failure was
determined so the conclusion cannot later be confused with a DimOS, Python,
Aurora or filesystem-only issue.

## Work Done

- Re-read the preserved SMART, dmesg and prior incident evidence.
- Recorded the six-condition decision standard and mapped every condition to
  observed evidence.
- Distinguished the decisive SMART, kernel and raw-sector evidence from
  downstream EXT4/application symptoms.
- Documented the successful Python/Aurora isolation A/B and why it proves a
  separate software defect rather than disproving the hardware failure.
- Recorded exact raw diagnostic SHA-256 hashes and approved external wording.
- Added replacement-SSD acceptance criteria and prohibited destructive tests.
- Limited the conclusion to persistent NVMe device/media hardware failure; no
  unsupported claim is made about a specific internal component.

## Decisions

- Reject the existing NVMe permanently from HE runtime use.
- Require replacement storage and the repository storage-health gate.
- Treat `critical_warning=0`, 99% spare and 0% wear as non-exculpatory because
  direct media-error evidence is present.
- Do not rerun invasive diagnostics on the powered-off failed installation.

## Current State

- Formal determination is recorded under `docs/he/evidence/`.
- Original evidence remains in the verified macOS recovery package.
- The Orin remains powered off.

## Resume Instructions

Use the approved wording in the determination document for supplier/internal
communication. After SSD replacement, follow its acceptance method before
resuming the blocked HE Goal.

## Open Questions

- Whether the SSD vendor will perform factory diagnostics to identify the exact
  internal component or initiating cause.
