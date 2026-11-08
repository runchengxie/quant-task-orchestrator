# Workflow Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the research console understandable and ground further work in inspectable evidence.
**Architecture:** Preserve independent Owners, read-only APIs and public/private boundaries. Add bounded standalone comparison and observation projections.
**Tech Stack:** Python stdlib, HTML/CSS/JavaScript, unittest and Playwright.
**Spec:** ../specs/2026-11-08-workflow-guidance-design.md

## Global Constraints
English default and zh-CN catalogs; no paid model calls, production schedule or live service changes. Public outputs contain only explicit safe fields.

## Review Focus
Unknown evidence/basis must never become comparable; malformed or symlink inputs fail closed; repeated rapid shadows do not imply long coverage; timeline unknown codes remain inspectable; guidance does not execute.

### Task 1: Terminology and recorded guidance
Files: site/* and browser tests. Add responsible system/capability/timeline explanations and recorded next-action evidence navigation; validate bilingual/mobile/auth regression.

### Task 2: Read-only economic comparison
Files: economic_results.py, cli.py, test_economic_results.py, paired docs/economic-results. Test matching/mismatching and missing basis, metric conventions, duplicate/nonfinite/extra/oversize/link input. Compare only pinned Owner-declared receipts; expose provenance limitations and no promotion.

### Task 3: Shadow observations
Files: shadow.py, shadow_history.py, cli.py and related tests, paired docs/shadow-observations. Record observed_at/duration_seconds; aggregate explicit configuration cohort without running Owners; test bounds, tampering and short windows. Run a small separately scoped real read-only check without installing schedules.

### Task 4: Real retained acceptance and delivery
Verify referenced Research retained artifacts and numerical pairs without invoking mutating campaign CLI. Record private evidence outside source and only generic findings publicly. Run full public checks, installed CLI acceptance and browser checks, independent review, current-main CI, commit/PR/merge/Pages. Keep pending GUI activation separate.
