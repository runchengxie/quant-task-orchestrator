# Contracts

## Workflow and approval

`quant.workflow.v1` requires `schema`, `idempotency_key`, `title`, `steps` and optionally a frozen `trigger`.
Each step requires `id`, `adapter`, `depends_on`, `skills`, with optional `requires_evidence`. IDs are bounded
ASCII identifiers. A graph must contain 1–100 unique steps and be acyclic with no
unknown dependencies. Titles should be operator-approved display labels: redaction
does not make arbitrary free text suitable for public publication.

`quant.orchestrator_config.v1` has exactly `schema`, `adapters`, `catalog`.
Adapters are operator configuration; a workflow references names rather than
inventing commands. The original two adapter shapes are shown here. Additional data/report/native-session
shapes and evidence gates are specified in [owner adapters](owner-adapters.md).

```json
{"kind":"runtime","command":["/immutable/release/backtest-job","--error-format","json","--database","/data/synthetic/jobs.sqlite","--artifact-root","/data/synthetic/artifacts","--result-root","/data/synthetic/results"],"request":"/data/synthetic/request.json","queue":true}
```

```json
{"kind":"research","command":["/immutable/research/bin/python","-m","strategy_app.ticknet.research.campaign_cli"],"config":"/private/config/approved-campaign.json","proposal_id":"existing-approved-proposal"}
```

Commands are argument arrays, never shell scripts. Interpreter module resolution
requires an installed owner in an immutable environment; do not use editable
production installations or mutable `current` symlinks for approved commands.
Executable bytes, explicit `.py` scripts, request/config bytes and Skill source
bytes are pinned in `quant.workflow_plan.v1`. Runtime additionally supplies its
own deterministic `plan_sha256`. Revalidation happens before every owner operation.
References inside an owner config remain governed and checked by that owner.

Approval binds the coordinator plan hash, allowed adapter kinds and a local
operator audit label. This label is not a cryptographic identity or remote auth.
Protect both configuration and database with OS permissions. Skill permissions are
metadata for review; they do not grant OS capabilities or expand owner authority.

## Skill catalog

Each entry has exactly `id`, `owner_repo` (`owner/repository`), absolute local
`source`, full 40-hex `revision`, relative repository `path`, `sha256`, `permissions`,
`input_contract`, `output_contract`. `git show COMMIT:PATH` verifies source bytes
without checking out or importing the owner. Sources stay in their owning repos;
the coordinator stores metadata, not a second copy of their implementations.

The workflow freezes selected entries. Updating a catalog does not update existing
workflows. This release verifies locks; it does not download/install packages or
execute Skills. Private source locators are omitted from query projections.

## State and event hints

Steps: `WAITING → DISPATCHING → RUNNING → SUCCEEDED | FAILED | CANCELLED`.
`UNKNOWN` requires reconciliation; `BLOCKED` preserves changed bindings or unmet
research evidence. Unknown owner states fail closed. Owner identities cannot change
once recorded. Workflow state is derived independently of owner evidence state.

`quant.workflow_event.v1` contains exactly `schema`, `event_id`, `workflow_id`,
`source`, `type` (`owner.changed`, `data.published`, or `report.published`). Identical event IDs are deduplicated; conflicting
reuse is rejected. An event persists only a hint. Regular polling rereads owners;
there is no trusted webhook, notification delivery or event-authentication layer.

## Query API

Bind only to IPv4 loopback. No CORS, browser writes or external interface enabled.

| Route | Contract |
| --- | --- |
| `GET /v1/workflows` | `quant.workflow_list.v1`, paginated workflow projections |
| `GET /v1/workflows/{id}` | `quant.workflow_view.v1` |
| `GET /v1/workflows/{id}/events?after=0` | `quant.workflow_events.v1`, up to 500 events after sequence |

The [live workbench](live-workbench.md) documents pagination, metrics and event-tail routes.

Writes return HTTP 405. Reads use SQLite read-only mode and never invoke owners,
recover leases, mutate task state or create a missing database. SQLite may create
coordination sidecars for an existing live WAL database. Views expose safe task
identities, timestamps, dependencies, budgets, selected Skill metadata and bounded
status codes. Raw owner payloads, commands, paths and reproduction locators stay
private. `freshness=last_observed_owner_state` and per-step timestamps distinguish
cached projections from current owner truth. Both `research_validated` and
`promotion_authorized` stay false; consult owner evidence for research decisions.

## Applicability and insight queries

A step can add typed `evidence_context`; Owner evidence can carry typed `scope`,
`assessed_at` and `valid_until`. See [evidence applicability](evidence-applicability.md)
for the distinction between market time, current validity and legacy checks.

| Route | Contract |
| --- | --- |
| `GET /v1/compare?before=ID&after=ID` | `quant.workflow_comparison.v1`; engineering identities only |
| `GET /v1/impact?proposal=JSON` | `quant.change_impact.v1`; consistent snapshot, no execution |
| `GET /v1/history?q=TEXT&snapshot_sha256=SHA` | `quant.research_history.v1`; pinned projection search |
| `GET /v1/evaluations` | `quant.evaluation_list.v1`; fixed trace checks, unverified provenance |

These queries share existing authentication and remain read-only. History import
and trace recording are explicit local CLI operations. Cache integrity does not
confer owner authority or turn trace scores into model evaluation.
