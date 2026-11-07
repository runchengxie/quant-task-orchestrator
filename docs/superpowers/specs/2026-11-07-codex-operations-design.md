# Codex execution and operational owner integration

Extend the existing workbench toward active, recoverable owner execution while
keeping research evidence and production adoption distinct. The workspace owner
explicitly selected direct Codex CLI integration and asked to advance all recorded
remaining areas. Start/resume/cancel and usage are engineering deliverables;
research qualification still needs independently available owner evidence.

## Approach

Use a Research-owned CLI lifecycle around installed `codex exec --json` and exact
`exec resume SESSION_ID`. Reuse the existing coordinator via a typed adapter.
The official CLI supports persistent session identity and token usage events.
App-server has richer turn interruption but would add another protocol/service;
it remains a documented future transport, not a second runtime in this increment.
Do not use `--last` or bypass permissions. The default task is tool-free/read-only.

## Boundaries

Research persists intent before detached supervision; tracks original key/session,
config/executable/prompt hashes, actual usage and receipt identity; and fences
resume/cancellation. Wall/turn ceilings are enforced. Observed token ceilings gate
later admissions; no hard in-flight token/dollar cap is claimed when CLI lacks it.
Actual model acceptance waits for the owner's explicit small-test scope. Unknown
cost stays unknown. Interruption of Codex never implies cancellation of independent
Runtime jobs. A model turn cannot assert PIT/economic validity or promotion.

Data Owner exploration identifies real content/availability evidence and missing
qualifications. Add a deterministic producer-owned verifier when reusable; never
retroactively invent `available_at` or promote an old diagnostic into qualified
research. Data/report execution needs exact approved owner commands, bounded
outputs and receipts. Live production ingestion/delivery/scheduler cutover remains
separate from isolated acceptance and is not used to make tests pass.

## Workbench operations

- Add `codex_task` owner adapter with explicit launch plan and fast polling,
  exact-key reconciliation, explicit resume and actual cancellation receipts.
- Add authenticated local read-only API with private token-file support and a
  browser memory-only login. Keep old loopback mode compatible. No public bind,
  CORS write endpoint, auth token in URLs/logs, or automatic proxy/security changes.
- Durable file inbox consumes bounded original event envelopes through Store.hint.
  Dedup, journal recovery and quarantine receipts preserve uncertainty. Notifications
  enter a durable local outbox with ack/dedup; no external messages are sent.
- Stage immutable merged releases, generate a dedicated read-only user service,
  SQLite backup and health checks. Retained data/config outside releases. Do not
  move shared current pointers or existing timers for validation.
- Install explicitly locked Skill bytes into external content-addressed storage
  with owner/contract/permission receipt; do not execute Skill code or silently
  replace existing installations.
- Measurements expose recorded token usage separately from observed coordinator
  wall time and CPU/model-cost unknowns. Preserve old database reads.

## Verification

Fail-first subprocess lifecycle tests cover duplicate/lost submissions, exact
resume, process interruption, timeout, cancellation identity, budgets, usage drift,
malformed outputs and private projections. File/Git/SQLite tests cover inbox replay,
outbox idempotency, install tampering, stable staging, backups and authenticated
GET-only API. Run complete coordinator/browser suites and affected provider tests.
Use actual installed owners and original scopes; real Codex calls only after the
owner supplies a budget. Record unresolved PIT/source/freshness/cancellation and
producer deployment limits explicitly. No production data or original acceptance
record is overwritten.

Official references: [CLI non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
and [App Server](https://learn.chatgpt.com/docs/app-server), checked against local
Codex CLI 0.167.0. Build artifacts and private acceptance records stay in project
DATA_ROOT task namespaces; settings/credentials stay under CONFIG_ROOT.
