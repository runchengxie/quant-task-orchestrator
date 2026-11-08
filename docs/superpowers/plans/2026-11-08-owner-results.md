# Owner Results Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect real Owner-declared receipts to strict comparison, inspection and recorded rechecks.
**Architecture:** Additive cache imports, read-only APIs and existing locale-based frontend; private standalone Research exporter merges first.
**Tech Stack:** Python stdlib, SQLite, HTML/CSS/JavaScript, unittest, Playwright.
**Spec:** ../specs/2026-11-08-owner-results-design.md

## Global Constraints
No private raw research in public source; unknown basis stays null; no automatic re-execution or promotion; no new model calls; stable merged releases only for deployed work.

## Review Focus
Pinned bytes must survive cache corruption; old read-only DBs must work without migrations; economic list/compare logout responses must be cleared; recorded recheck must not imply Owner refresh; GUI activation preserves prior workflow states and rolls back if health fails.

### Provider task
Research root research_economic_export.py and focused tests/docs: hash-pinned bounded safe reads, supported source schemas, opaque IDs, source-proven metrics, honest unknown basis. Run actual retained export; provider PR and merge before consumer.

### Cache and recheck task
Public economic_cache.py, recheck.py, store.py/api.py/cli.py, focused tests: single-file hash imports, typed pagination, integrity-checked reads, exact-pin comparisons, no-table fallback; evidence requirement queries using scope/TTL with no state mutation.

### GUI and evaluation task
Live insights list/select/compare UI with all labels localized and stale auth guards; deterministic not-run Codex task plan and independent rubric. Test empty/error/unknown/duplicate inputs, public/private browser and logout races.

### Acceptance and delivery
Actual provider receipts imported in isolated consumer DB; installed wheel real-backup browser and recheck; read-only freshness/integrity observations separately retained. Full relevant checks, independent review, current-main PR validation, provider-first merges, Pages. Stage merged release and upgrade only intended local GUI with backup/rollback; retained workflow states unchanged.
