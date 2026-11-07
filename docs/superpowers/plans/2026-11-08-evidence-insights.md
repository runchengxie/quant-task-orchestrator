# Evidence Insights Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans task-by-task.

**Goal:** Scoped evidence and useful research insights with a standalone public experience.
**Architecture:** Existing SQLite coordinator and read-only GUI, owner-exported snapshots.
**Tech Stack:** Python stdlib, versioned JSON, SQLite, JavaScript locale catalogs.
**Spec:** [Design](../specs/2026-11-08-evidence-insights-design.md).

## Global constraints

No private source imports in public code, no raw owner payload projection, no
new inference or external sends, no production schedule changes. Scope and TTL
must reject missing/invalid proof; preserve legacy workflows and historical states.

## Review focus

Market time differs from assessment time. Partial scope cannot satisfy a gate.
Expired data cannot be revived by cached status. Comparison cannot claim financial
causation. History IDs must remain stable across source snapshots. Reference eval
must never be presented as model quality. Demo must work from an installed wheel.

- [x] Add typed scope/TTL projection and validation; fail-first mismatched/expired gates.
- [x] Add comparison and full-database impact preview with private field exclusion.
- [x] Add Research read-only history export and consumer snapshot search.
- [x] Add fixed trace evaluation and no-dependency synthetic demo.
- [x] Integrate CLI/API/UI, language catalogs, comparison/history/evaluation views.
- [x] Reconcile root documentation with current capabilities and limitations.
- [ ] Run installed owners, browser/demo, independent review and checked PRs.
- [ ] Install merged release with preserved state; clean only this task resources.

Local acceptance: 149 configured-owner tests passed without skips; installed
wheel and all four read-only insight panels passed outside the source checkout.
Independent review added negative regressions for malformed evidence fallback,
source impersonation, nested cache fields, source ID collision and bounded WAL
exports. No model was invoked; reference scores remain explicitly unverified.
