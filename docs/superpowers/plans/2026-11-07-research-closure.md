# Research Closure Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for each bounded deliverable.

**Goal:** Turn remaining integration and operational gaps into verified interfaces and evidence.
**Architecture:** Existing stdlib coordinator, separate Research/data owners, isolated acceptance.
**Tech Stack:** Python 3.12+, SQLite, owner CLI/MCP, browser JavaScript.
**Spec:** [Design](../specs/2026-11-07-research-closure-design.md).

## Global constraints

Public source has no private strategies/paths/credentials. No production schedule
cutover or external message sends. Live model budget: one session, two calls,
300 seconds; other work uses no inference. Unknown PIT/usage/cost stays unknown.

## Review focus

Receipt attachment cannot invoke model work. Corrupt or moved backup targets
must not overwrite state. Uncertain notification sends cannot be replayed.
Tool profiles cannot accept arbitrary caller commands/paths. New observations
cannot be relabeled as historical PIT verification.

- [x] Complete live tool-free session resume and record actual source/usage/context.
- [x] Add receipt-only Codex observation tests first, implement adapter and CLI docs.
- [x] Add recovery/notification/migration operations and CLI tests before integration.
- [x] Run installed report Owner and deterministic multi-owner DAG acceptance.
- [x] Implement and test Research tool gateway/MCP; merge provider before consumer.
- [x] Generate bounded offline normalization/PIT evidence or record exact blockers.
- [ ] Run complete checks, independent review and remote CI; merge consumer.
- [ ] Install merged release and verify private GUI; retire only this task resources.

User selected the read-only data-readiness shadow pilot and local-only notifications.
The data owner generated four normalized components and indicator-only PIT; the
four-component PIT stays blocked on statement-template identity. Shadow has no
timer or cutover effect. A controlled reader installation passed zero-inference
CLI/MCP/v2 compatibility. Final validation: 108 tests passed without skips.
