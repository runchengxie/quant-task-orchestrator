# Owner adapters and conformance

Five explicitly registered adapter kinds are available. Discovery and preflight do
not grant execution permission. Every workflow approval binds its complete plan.

```sh
quant-task capabilities
quant-task conformance --config "$TASK_CONFIG"
quant-task --database "$TASK_DATABASE" metrics
quant-task --database "$TASK_DATABASE" recovery "$WORKFLOW_ID"
```

`conformance` invokes each configured owner's bounded preflight/read operation,
checks its envelope/identity and pins inputs. It reports `fault_injection_tested=false`:
only the test suite exercises faults. It is not a load, research or production
acceptance certificate. Keep private configurations and plans outside repositories.

| Kind | Owner operation | Success means |
| --- | --- | --- |
| `runtime` | Existing plan/submit/lookup/inspect/result/cancel | Bound compute result verified |
| `research` | Advance an existing approved campaign proposal | Owner process concluded; conclusion remains separately visible |
| `data` | `marketdata contract assess` | Frozen publication metadata/freshness checks passed; content/PIT unknown |
| `report` | `quant-market-brief` | Existing report/manifest identity and owner content validation passed |
| `native_session` | `python -m strategy_app.native_session_inspect` | Retained segment's config/session/events verified; no model launch |

An optional `owner_revision` is a full 40-hex **declared** source revision. Executable
and explicit script bytes are hashed, but a declaration is not proof of installed
module provenance. Use a genuinely immutable owner environment/release and retain
its wheel/build digest. Never point an approved interpreter invocation at editable
or mutable modules. No adapter imports owner business modules into the coordinator.

## Data assessment

```json
{"kind":"data","command":["/immutable/data/bin/marketdata"],"artifacts_root":"/data/synthetic/assets","contract":"/data/synthetic/contract.json","asset":["daily"],"target_date":"20261030","require_start_date":null}
```

The adapter pins the contract and owner-resolved manifests, checks snapshot
identity on every read, and rejects any failed owner check. Missing freshness also
blocks. Exit zero alone does not establish readiness. It never calls a producer,
passes an output path, requests a vendor, or claims data content/PIT verification.

## Existing report

```json
{"kind":"report","command":["/immutable/intel/bin/quant-market-brief"],"input":"/data/synthetic/daily_report.json","manifest":"/data/synthetic/publication.json","expected_date":"2026-10-02","previous_report":null}
```

Input, manifest and optional immutable parent are pinned. The owner verifies report
semantics and public manifest consistency. The coordinator retains only allowlisted
digest evidence and status; raw reports, private paths and reproduction locators do
not enter the query projection. It does not publish or deliver a report.

## Retained native session

```json
{"kind":"native_session","command":["/immutable/research/bin/python","-I","-m","strategy_app.native_session_inspect"],"config":"/private/campaign.json","receipt":"/private/segment/receipt.json","events":"/private/segment/native.jsonl","session_id":"original-session","resume_receipt":"/private/original/receipt.json"}
```

`resume_receipt` is optional/nullable for a fresh segment. The original receipt is
required for resumed grading without another proposal. The owner independently
regrades successful tools and turn completion, binds all bytes and the original
session, and returns `quant.native_research_session_inspection.v1`. A successfully
inspected interrupted segment remains blocked, with `execution_complete=false`.
This release attaches to immutable retained sessions. Starting a new paid session,
choosing models or restoring owner compute budgets is not exposed.

## Explicit evidence gates and publication hints

A step can require independently verified evidence from its direct dependencies:

```json
{"id":"qualified-backtest","adapter":"runtime","depends_on":["data"],"skills":[],"requires_evidence":{"data":["historical_pit","input_integrity"]}}
```

Both checks must be `verified`; unknown/missing/not-applicable do not pass.
The existing data assessment deliberately cannot satisfy these stronger checks.
Use only a genuinely approved diagnostic workflow when those claims are not needed;
never weaken a qualified study just to make its status green.

A workflow may freeze an optional `trigger`:

```json
{"source":"quant-market-data-platform","event_type":"data.published"}
```

Send `quant.workflow_event.v1` through the existing `event --file` operator command
with the original `workflow_id`, unique `event_id`, matching `source` and `type`.
Allowed types: `owner.changed`, `data.published`, `report.published`. Unapproved
workflows remain unapproved. Source labels are **not transport authentication**;
a hint only wakes checks on an already approved, frozen plan. Every actual owner
input is revalidated. No external webhook, message delivery or production timer
was installed. Future scheduled adoption must avoid duplicate submission authority.
