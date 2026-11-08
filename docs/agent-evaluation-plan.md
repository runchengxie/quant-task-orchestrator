# Prepare a real agent evaluation

[中文](agent-evaluation-plan.zh-CN.md)

`quant_task_orchestrator.agent_eval_plan.build_agent_evaluation_plan()` returns a
versioned JSON-compatible read-only plan. It needs no model name and makes no
model, shell, owner or filesystem calls. The plan is `not_run`,
`model_evaluated: false`, with unknown outcome and null score/trace. Creating it
provides no new evidence of Codex reliability. Previous call budgets are not
renewed by this plan: a real evaluation requires an explicit new call budget.
The conservative recommendation is at most two model calls, one original session
and five minutes, with immediate stop at exhaustion.

The seven scenarios reuse the exact versioned harness cases: wrong handle, wrong
artifact, bounded calls, missing PIT evidence, submit boundary, unknown usage and
original-session recovery. Real agent responses must explain the observed tool
results, cite the actual admitted evidence and abstain when evidence or permission
is missing. Never populate this plan with invented traces or interpret an empty
run as passing. `evaluation.py` checks recorded protocol traces; it does not judge
whether an agent understood research evidence.

An independent human or reviewer must assess the actual responses against the
included rubric. Record exact authorized handles, profile and content hashes,
command-file pins, missing evidence, expected abstention, original session identity
and measured usage where available. Missing token/cost telemetry remains unknown.
A snapshot receipt must match `research.tool-response/v1`, handle, profile hash,
resource kind and content hash, with `snapshot: true`. Hash-verified bytes establish
input integrity; historical PIT, freshness and economic validity need separate
evidence. All required criteria need observed real responses and independent
assessment before an overall pass is possible.

## Continue observing data safely

The existing frozen-raw monitoring proposal is content-integrity-only, local-only,
and records `installed: false` and `enabled: false`. It cannot establish daily
ingestion freshness. Review retained observations against the exact frozen
cohort/config pins; retain changed or missing pins as failures. Do not silently
replace that cohort with a new publication. Enabling a timer is a separate action.

The data owner's existing `scripts/operations/data_status.py --root
"$DATA_PLATFORM_ROOT" --expected-date YYYYMMDD` is a read-only freshness overview.
Choose the expected trading date explicitly. It neither infers the calendar target
nor requests providers, repairs services or writes receipts. Save stdout only in a
new task-specific data directory if retention is desired. Omit `--with-systemd`
unless service inspection is needed; that opt-in checks five known services with
five-second timeouts. Read `needs_attention` and component states: exit zero means
an overview was produced, not data acceptance. Historical evidence defaults to six
hours; missing, malformed, future or timezone-naive evidence cannot establish
readiness. Supplemental evidence remains unverified. Record observation time,
expected date, source revision, receipt hashes and missingness separately from the
frozen integrity result. This plan does not execute that check or acquire data.

`marketdata contract capture` pins publication metadata, not Parquet bytes or
freshness; its receipt explicitly has `data_content_verified: false` and
`atomic_transaction: false`. The execution-input audit writes research slices and
`readiness.json`; it is not the read-only overview and reconstructed PIT does not
provide revision-safe historical vintages. Existing private adapter configuration
has raw-observation and research-readiness handles; those names alone establish no
freshness threshold or research qualification.

Owner references: [data overview](https://github.com/runchengxie/quant-market-data-platform/blob/main/docs/operations/data-status.en.md),
[metadata snapshot](https://github.com/runchengxie/quant-market-data-platform/blob/main/docs/operations/published-asset-snapshot.en.md),
[execution readiness](https://github.com/runchengxie/quant-market-data-platform/blob/main/docs/operations/execution-input-readiness.en.md).
