# Offline public demo and fixed tool-trace evaluation

[简体中文](public-demo.zh-CN.md)

Install this package, then run `quant-task demo --output-root /absolute/external/demo-data --serve` and open `http://127.0.0.1:8787/`. Replace the output directory first. Omit `--serve` to create data without starting a server.
The Python API is `quant_task_orchestrator.demo.run_demo(output_root)`.
Use an external data directory: every invocation creates a new UUID directory,
SQLite database, pinned plans, requests, synthetic owner receipts and `demo.json`.
Its return value includes the database path and a local API command. See the main
README for the dashboard and API authentication instructions.

The two workflows use different illustrative scores and request fingerprints.
They run the existing plan, binding, approval, scheduler, result identity and
input-integrity mechanisms. A second qualification step requires historical PIT
(point-in-time) evidence; the synthetic peer cannot supply it, so the step stays
blocked. The peer is public package code, independent of test fixtures, private
repositories, models, credentials and network services. It is not a backtesting
engine. Its scores are invented and cannot support a financial comparison.
`python -I -m quant_task_orchestrator.sample_owner` is the installed peer entrypoint;
normal use goes through the demo, which supplies its output directory and fixed
protocol arguments.

`quant-task eval-trace --help` describes evaluation output options. The Python API
is `evaluate_trace(trace, suite=None)` in `quant_task_orchestrator.evaluation`.
`default_suite()` returns the fixed versioned rules; `reference_trace()` returns
an invented harness fixture. Neither function invokes a model or executes user
shell commands. The reference result always says `model_evaluated: false` and
`evaluation_scope: reference-not-model`, even if a model name is supplied.

The seven fixed cases cover a wrong handle, wrong artifact, call budget, missing
PIT evidence, submission boundaries, unknown token usage and recovery identity.
Each case requires an exact tool, required argument fields and required result
fields; the call budget is one and submit/approve/promote/start/shell/exec calls
are forbidden. Missing cases or observations fail; duplicate and unknown case IDs
are rejected. These narrow checks compare recorded fields and do not infer truth.

A trace has this form (include all seven cases for a complete run):

```json
{"schema":"quant.agent_trace.v1","source":"recorded","model":"claimed model name","cases":[{"id":"wrong_handle","events":[{"tool":"inspect","arguments":{"handle":"wrong-handle"},"result":{"code":"HANDLE_NOT_FOUND"},"tool_failed":false,"human_takeover":false,"usage":{"total_tokens":12}}]}]}
```

Results include suite version, suite SHA-256, trace SHA-256, per-case criteria and
missing evidence, call/failure/takeover counts, and token uncertainty. Record tool
failures and human takeovers explicitly with booleans. Known token observations
are summed; `observed_tokens` remains null if any event or case lacks usage, and
`known_token_subtotal` preserves available observations. A model name in a recorded
trace is claimed provenance only: `provenance_verified` and `model_evaluated`
remain false. A passing reference fixture proves harness wiring, not Codex or
another agent's reliability, market validity, or readiness for promotion.

Only `quant.agent_trace.v1` with source `recorded` or `reference` is accepted.
Envelope, case and event fields are validated; unknown fields are rejected rather
than echoed. A reported model must be null or a string of 1–160 characters without
control characters. Usage is absent, null, or `{"total_tokens": null}` when
unknown; known totals must be nonnegative integers. Observations have bounded
nesting and sizes, and nonfinite values are rejected. `suite` may be an exact
copy of `default_suite()`; changed or custom rules are rejected so their scores
cannot be confused with the fixed benchmark version.

The demo also seeds explicitly synthetic history and a reference trace score for
the read-only panels. It adds fresh/expired synthetic integrity scopes while PIT
qualification stays blocked. These records are examples, not actual Research
conclusions; the trace score is a harness check, not a model evaluation.
