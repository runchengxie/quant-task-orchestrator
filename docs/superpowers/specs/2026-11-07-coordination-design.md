# Research workflow coordination

Build an independently licensed public coordinator with a CLI, read-only TUI,
loopback JSON API and a GitHub Pages synthetic demo. The coordinator owns workflow,
assignment and event identities; Runtime owns compute and publication; Research
owns admission, budgets, review and promotion. The demo is static, explicitly
synthetic and does not contact production services.

## Approach

Keep the backtest lifecycle intact and add a thin Python 3.12+ standard-library
SQLite coordinator. Extending Runtime would mix financial execution and research
coordination; adopting a new distributed workflow framework would add an
unmeasured operational dependency. No third-party source code is copied.

Workflow steps reference operator-configured adapters, never shell commands.
Runtime uses plan-bound queued submission, lookup, inspect, result and cancel.
Research reconciles an existing, operator-approved campaign proposal through its
fixed CLI. Native Agent sessions remain owned by Research; launching a new model
session and choosing a proposal are not exposed in v0.1.

## Contracts

A workflow freezes a DAG, adapter configuration and content-hashed Skill locks.
An explicit approval binds the complete plan hash and allowed adapter kinds.
Assignments persist before remote effects. Lost responses reconcile the original
idempotency key; an uncertain mutation is never automatically repeated without proving an existing owner job. A single
nonblocking process lock fences scheduler instances. Owner results are verified
before dependent steps start. Cancellation stops new dispatch and reconciles
active owners; it does not delete owner evidence.

Skills carry owner repository, exact Git revision, file path, content digest,
permissions and input/output contract identifiers. Verify local source bytes at
that revision without installing or importing owner code. Existing workflows keep
the frozen catalog even if the configured catalog changes.

Persisted events are idempotent wake-up hints, not authenticated facts or new
authority. Poll owners before changing assignment state. SQLite transactions bind
state transitions and audit events. The query API and TUI redact owner payloads,
paths and private reproduction locators by using an explicit projection.

## Acceptance and limits

Test DAG/authorization, plan drift, duplicate submission, interruption recovery,
uncertain responses, cancellation, malformed owner output, Skill tampering and
private projection. Exercise real Runtime against synthetic inputs when installed.
Do not install production services or migrate cron/systemd jobs. No distributed
leases, live trading, automatic promotion or paid model evaluation. CLI/API use
English; static demo has an explicit persistent English/Chinese switch.
