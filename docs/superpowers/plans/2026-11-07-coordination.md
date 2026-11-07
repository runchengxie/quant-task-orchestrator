# Workflow Coordinator Implementation Plan

> Execute inline with superpowers:executing-plans; verify each deliverable before publication.

**Goal:** Public thin coordinator, owner adapters, locked skills, TUI/API and synthetic Pages demo.
**Architecture:** Python standard library, SQLite, fixed owner CLIs, read-only projections.
**Tech Stack:** Python 3.12+, SQLite, unittest, HTML/CSS/JavaScript.
**Spec:** [Design](../specs/2026-11-07-coordination-design.md).

## Global constraints

No private source or real data; no production schedule changes; no copied external code.
Owner CLI effects require a persisted plan approval. Read APIs never reconcile owners.

## Review focus

- A restart during an owner call must reconcile, never repeat an uncertain mutation.
- Changed command/config/request/Skill bytes must invalidate approval before dispatch.
- Invalid DAGs, unknown adapter kinds and mismatched owner identities must fail closed.
- A completed computation must never imply verified research or strategy promotion.
- The public projection and Pages fixture must exclude private owner payloads and paths.

## Tasks

- [x] Contracts and store: failing unittest cases for DAGs, idempotency, approvals,
  persistent events, immutable Skill locks and redacted views; implement and run suite.
- [x] Owner adapters and scheduling: fail-first tests for lost receipts, recovery,
  result verification, dependent blocking, cancellation and single scheduler fencing;
  implement Runtime and existing Research campaign adapters and run suite.
- [x] Operator interfaces: CLI, read-only TUI and loopback API sharing projection;
  subprocess tests and optional real Runtime synthetic acceptance.
- [x] Publication: bilingual README, operation contracts, synthetic Pages demo,
  dependency-free CI, public content review, PR/merge and Pages deployment verification.

## Execution record

Implemented inline under the user-confirmed scope. Read-only live TUI/API plus a
static browser demo were added; full authenticated GUI remains out of scope.
Independent review found request-identity adoption, stale Research polling,
parallel failure abandonment, presentation-limit starvation and cancellation
handoff observation defects. All received fail-first regression tests and fixes.
Additional tests cover cancelled dependencies and budget-field projection.
No production timers, owner databases, credentials or private source were changed.
