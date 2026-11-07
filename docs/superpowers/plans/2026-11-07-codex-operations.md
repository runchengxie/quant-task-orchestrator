# Codex and Operations Implementation Plan

**Goal:** Active bounded Codex owner execution plus useful operational delivery and real evidence readiness.
**Architecture:** Research lifecycle CLI, typed coordinator adapter, durable local event/outbox, private read-only deployment.
**Spec:** [Design](../specs/2026-11-07-codex-operations-design.md).

## Constraints and review focus

No new paid calls until accepted test scope; no historical availability fabrication;
no unrelated production schedule/data/security changes. Preserve original session,
workflow and event identities. Bind code/input bytes and fail closed after uncertainty.
Keep source revision, tests, model acceptance and deployment acceptance separate.

- [x] Research lifecycle: fail-first process tests, plan/start/inspect/resume/cancel,
  budgets, token accounting, independent worker and immutable receipts.
- [x] Data/real study: examine latest owner-sealed evidence and #649, improve bounded
  verification where useful, document exact missing prerequisites without false green.
- [x] Public integration: typed codex adapter, explicit resume CLI, token projection,
  actual owner/consumer compatibility and cancellation tests.
- [x] Operations: durable inbox/outbox, installed Skill receipts, stable release/unit,
  backups, authenticated local query API and browser login.
- [ ] Acceptance: complete tests, installed owner checks, optional bounded Codex
  acceptance after user input, actual read-only staged service check and honest limits.
- [ ] Independent review, provider-before-consumer checked PRs, Pages verification,
  cleanup only task resources. Production adoption decisions remain separately recorded.

Qualification is deliberately partial: real first-turn completion and exact-session
second-turn admission/cancellation are verified; completed live resume and
research-capable tools are not. Raw bytes are verified, PIT remains unknown.
Service generation/staging is implemented; adoption is separately recorded.
See [increment validation](../../codex-operations.md).
