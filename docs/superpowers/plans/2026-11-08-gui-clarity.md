# GUI Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make progress, blockers and next steps readable before technical details.
**Architecture:** Preserve the read-only API and existing vanilla frontend. Live and synthetic Pages share information hierarchy, without sharing private data.
**Tech Stack:** HTML, CSS, JavaScript, Python Playwright.
**Spec:** ../specs/2026-11-08-gui-clarity-design.md

## Global Constraints
English default and zh-CN catalogs; no API mutations, private data, framework installation, model calls or production scheduler changes.

## Review Focus
- Loaded counts must not imply global coverage.
- Successful execution must not imply research validation.
- Polling must preserve expanded details.
- Logout must clear private content including delayed responses.
- Mobile and translated text must fit.

### Task 1: Live inspection hierarchy
Files: site/live.html, live.js, live.css, live-locales.js; tests/live_browser_smoke.py.
- [x] Add assertions for loaded summaries, collapsed technical panels and polling preservation; verify failure.
- [x] Implement scoped summary filters, selected workflow guidance and progressive disclosure. Preserve existing API fetches and DOM identifiers.
- [x] Run live and insights browser checks plus node syntax checks.

### Task 2: Synthetic Pages clarity
Files: site/index.html, app.js, locales.js, demo-data.js, styles.css; tests/browser_smoke.py.
- [x] Add scenario and readable summary assertions.
- [x] Implement attention-first presentation with success, evidence blocking and failure cases.
- [x] Run public browser checks.

### Task 3: Review and delivery
- [x] Update paired workbench documentation and run full unit, syntax, compile and browser validation.
- [ ] Review diff and test prospective current-main version. Commit, push, PR, merge after required CI and verify Pages.
