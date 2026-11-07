# Research workbench and bounded owner integration

## Intent and scope

Advance the seven next-stage directions requested by the workspace owner: an
actual retained research workflow acceptance, live read-only GUI, explicit evidence
panel, actionable recovery, adapter conformance, data/report owner integration,
and bounded native Agent session coordination. Include operational measurements.
Keep initial workflow/plan contracts readable, preserve authoritative owner states,
and distinguish exploration, protocol acceptance and actual research acceptance.

## Approaches

Extend the existing standard-library coordinator and reuse the current visual
language in a same-origin local GUI. A separate frontend/service would duplicate
query contracts and release machinery. Changing production schedulers would mix
feature validation with operational cutover. The selected approach is the existing
coordinator with additional fixed adapters; no production migration is included.
The user's request authorizes advancing the stated directions; routine interface
and implementation choices below are engineering choices, not additional user
preferences.

## Components and authority

- Serve a bundled live read-only page and API together on IPv4 loopback. Reject
  nonloopback Host headers, do not enable CORS or HTTP mutations. The public Pages
  demo remains synthetic and can link to the live interface instructions.
- Extend workflow projections additively with evidence dimensions, recovery action
  codes, source timestamps, pinned code identity and task lifecycle measurements.
  Unknown PIT, economics, model cost or execution semantics remain unknown.
- Owner invocations retain fixed arguments, bounded time/output, exact input/code
  pins and durable dispatch identity. Extract a deterministic adapter registry with
  conformance tests. No arbitrary shell/plugin discovery or private code imports.
- Optional frozen publication triggers wake only already approved workflows. Source
  labels are hints, never authentication; every Owner input is independently rechecked.
- Add read-only data assessment and report-verification adapters using existing
  owner CLIs. Validate owner envelope/schema/identity and project only allowlisted
  evidence. Their success acknowledges owner verification, not new data production
  or automatic report delivery. New production/notification schedules require a
  separate coordinated adoption step.
- Bound native research sessions to the existing owner wrapper/configuration,
  approval digest, immutable output receipt, session identity and explicit compute/
  model scope. Prefer attaching/reconciling an owner session before opt-in launch;
  never start a paid model call merely to test this release. Resume uses the exact
  owner receipt/session and never a latest-session shortcut.
- Investigate retained approved research acceptance through designated owner
  records only. Reuse an existing immutable run or isolate all mutable state under
  a new project task data directory. No private strategy/configuration is published.
  Missing evidence is an accepted blocked outcome, never manufactured qualification.

## Projection and interface

`quant.workflow_view.v1` keeps existing fields. Each step adds `evidence` with six
independent checks (`input_integrity`, `historical_pit`, `execution_semantics`,
`independent_review`, `economic_conclusion`, `promotion`), a `recovery` object
containing stable action codes, `owner_revision` when explicitly configured, and
`metrics` from recorded coordinator timestamps/counters. Owner data is parsed at
the adapter boundary, never passed through to GUI. References exposed publicly
contain only digest identities and safe labels, not private URLs or paths.

The local UI polls `/v1/workflows` and `/v1/metrics`, selects a workflow/step,
reads `/v1/workflows/{id}/events`, displays dependencies, evidence and recovery,
and distinguishes API outage from an empty database. English is default; Chinese
is explicit and persists. No approval, cancel, retry, model launch or promotion
buttons are offered by the live read-only UI.

## Validation

Fail-first unit/CLI tests cover additive migrations and legacy databases, privacy,
unknown evidence, stale observations, lifecycle timing, event/call idempotency,
all adapter shapes, cancellation/recovery, malformed owner schemas, paginated
queries and GUI/API read-only behavior. Browser tests run against an actual local
coordinator database; static Pages tests continue separately. Installed owner
acceptance uses synthetic fixtures when available; retained private acceptance
records stay outside the public repo. Test actual native Agent receipt/resume
binding without a paid model launch. Record precisely what remains unvalidated.
