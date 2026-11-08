# Live research workbench

[简体中文](live-workbench.zh-CN.md)

The local GUI reads the same coordinator database as the TUI. It shows actual
workflow dependencies, step identities, observations, evidence dimensions,
recovery advice, pinned owner revisions and coordinator measurements.
The public [Pages demo](https://runchengxie.github.io/quant-task-orchestrator/)
continues to use fictional browser-local data.

```sh
quant-task --database "$TASK_DATABASE" serve-api --host 127.0.0.1 --port 8787
```

Open `http://127.0.0.1:8787/`. The page and API share an origin. It polls every
five seconds, supports workflow pagination and filtering, and keeps the selected
English/Chinese locale when browser storage is available. UTC is explicit.
An API outage is distinct from an empty database; last owner observations are not
presented as current owner truth. Refresh and selecting steps only query state.
HTTP approval, cancellation, retries and model launches are not exposed.

The wheel includes the static assets, so an installed immutable release can serve
the UI without a source checkout. The server binds to IPv4 loopback and rejects
nonlocal Host/Origin headers. It provides no remote identity/authentication layer.
Private remote access requires a separately designed deployment; do not change
its bind address or expose the local database API as a public service.

## Daily inspection

Start with **Needs attention**, **In progress** or **Execution completed**. These
clickable cards count only loaded workflows; the loaded/total label makes
pagination coverage explicit. Click a selected card again to clear its filter.
The operating metrics disclosure contains whole-database measurements.

Select a workflow to see execution and research qualification separately, followed
by recorded blocker codes and suggested next actions when available. Suggestions
do not authorize execution. The dependency graph helps locate a step; evidence
remains visible below it. Workflow hashes, permission facts, run/Agent usage and
event history are available in disclosures. Expanded detail panels survive polling
for the same workflow; selecting another workflow resets them.

The public demo illustrates successful computation, missing evidence and failed
execution. Its controls only change synthetic browser-local state.

## Evidence and recovery

Each step exposes six independent dimensions: input integrity, historical PIT,
execution semantics, independent review, economic conclusion and promotion.
A data assessment validates publication **metadata**, so its step may succeed
while `input_integrity` and historical PIT remain unknown. A verified report
payload is descriptive evidence; it does not prove its factual claims or delivery.
A completed native session is not research acceptance. Promotion remains unknown
and `promotion_authorized=false` throughout the coordinator.

Recovery advice contains stable action codes, not executable authorization.
Unknown submission state points to the original key/owner. Changed inputs require
restoring the approved binding. Pre-dispatch blockers remain stopped rather than
adopting somebody else's existing job. Research cancellation still requires the
owner/operator handoff. New execution requires deliberate scope and approval.

## Measurements

Waiting/running/blocked/unknown durations are observed coordinator occupancy,
not measured CPU time. Owner call counts, protocol failures and command wall time
are measured by the coordinator. Operator action counts cover recorded approvals
and cancellation requests. These are not a complete human-effort measure.
Model cost and CPU accounting stay `null` when the owner does not supply them.
Legacy databases report unavailable measurement coverage until observations start.
Repeated identical polls update observation freshness without inventing state changes.

## Query routes

- `GET /v1/workflows?limit=100&offset=0`: projections and pagination, maximum 1,000 per page.
- `GET /v1/workflows/{id}`: a workflow with evidence, recovery and measurements.
- `GET /v1/workflows/{id}/events?tail=100`: newest chronological event window, maximum 500.
- `GET /v1/workflows/{id}/events?after=SEQUENCE`: existing sequential event pagination.
- `GET /v1/metrics`: counts across the whole database, independent of list pagination.

All read-only routes open an existing database without migrations or owner calls.
Writable coordinator operations add auxiliary tables; old workflow, plan and step
records remain readable. Final state and validated observation are committed in
one transaction. Back up through SQLite's backup API before upgrading retained state.
