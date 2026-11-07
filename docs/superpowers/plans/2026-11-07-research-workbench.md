# Research Workbench Implementation Plan

> Execute with focused file ownership and superpowers:executing-plans; tests precede implementation.

**Goal:** Advance all seven agreed directions with reviewable code and bounded owner acceptance.
**Architecture:** Existing Python stdlib/SQLite coordinator, same-origin read-only GUI, fixed owner adapters.
**Tech Stack:** Python 3.12+, SQLite, unittest, HTML/CSS/JavaScript, Playwright.
**Spec:** [Design](../specs/2026-11-07-research-workbench-design.md).

## Global constraints

No production schedule or authoritative database changes; no private source/config/data in public commits;
no paid model invocation for testing. Preserve old workflow/plan/database readers.

## Review focus

- A successful owner process must not imply verified PIT/economics/promotion.
- Resumed/attached sessions must retain exact config, receipt and session identity.
- Local GUI reads must never dispatch or expose private locators/raw owner diagnostics.
- Existing SQLite databases must remain readable before and after additive migration.
- Owner updates, missing fixtures and unavailable real study evidence must be reported honestly.

## Tasks

- [x] Read-only exploration: record exact Research/native Agent and data/report owner contracts,
  retained approved acceptance candidates and remaining evidence gaps.
- [x] Add projection/recovery/measurement tests; implement focused evidence.py/recovery.py/metrics.py
  and additive SQLite observations with bounded allowlisted data. Preserve legacy behavior.
- [x] Add registry/conformance tests; implement fixed data/report/native-session adapters using
  discovered owner contracts and hashes, no duplicated owner business computations.
- [x] Build local live GUI using projections; serve bundled static resources alongside API,
  enforce loopback read-only routes, add database pagination and API/browser acceptance.
- [x] Run isolated installed owner synthetic acceptance and retained-study checks as authorized;
  retain private receipts under the owning data root, record public-safe conclusions only.
- [x] Review all changes; run complete tests, owner integrations, packaging and browser checks;
  update docs/demo, deliver via checked PRs, verify Pages, and clean this task's branches/worktrees.

## Execution notes

Owner interface exploration found reusable read-only data/report contracts.
Research added a top-level lightweight native-session inspection CLI and canonical
stdlib grade/session/resume helpers, preserving existing helper exports. Actual
wheel validation exposed eager training imports in the original namespace and
was corrected before delivery. Retained initial/resumed segments are inspected;
qualified continuation stays blocked on unknown PIT, with no fresh model calls.

Independent review found pre-dispatch gate bypass, terminal/evidence transaction
separation and premature Research identity binding. Fail-first regression tests
reproduced all three; fixes preserve dispatch intent, atomic final observations,
and owner identity checks. Metadata-only data assessment keeps input byte
integrity unknown. Publication triggers remain hints for frozen approved plans.
