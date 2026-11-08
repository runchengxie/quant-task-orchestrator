# Read-only shadow observations

[简体中文](shadow-observations.zh-CN.md)

A successful shadow run establishes readiness only at that recorded observation.
Repeated runs within minutes do not establish daily stability. Keep observing the
same approved configuration over a meaningful time window before making an
operational decision. Shadow evidence never authorizes research promotion or a
production schedule change.

`summarize_shadows(root, expected_config_sha256, *, limit=500)` in
`quant_task_orchestrator.shadow_history` reads existing `assessment.json` records
and returns `quant.data_shadow_history.v1`. Supply the exact approved lowercase
SHA-256 configuration digest. The root must contain only immediate UUID-hex run
directories; put unrelated files elsewhere. The function never executes adapters,
reads workflow databases or follows raw-data paths. It installs no scheduler or
notification transport and changes no files.

The summary counts independent run IDs, statuses, failures, records for other
configuration pins, invalid records, unknown timestamps and supplied measured
latencies. Other pins have separate status counts and never contribute to the
requested pin's observation window. Results contain no private paths or raw step
payloads. Missing or unsafe roots and malformed or unreadable records produce
explicit errors. Invalid function arguments raise `ValueError`.

Observation time comes exclusively from timezone-qualified `observed_at` in each
local assessment. Missing legacy timestamps remain unknown. Directory names and
file modification times never establish timing. Future timestamps are invalid.
Optional `duration_seconds` must be a finite nonnegative measured duration no greater than 31 days; absent
measurements remain absent. Local records are evidence supplied by the producer,
not cryptographic proof that runs occurred or that their clocks were correct.

The minimum observation-window gate requires at least seven successful independent
runs, at least seven distinct UTC dates and a span of at least seven full days.
Any error, different configuration, unknown timestamp or non-success status makes
the window insufficient. These are minimum monitoring gates, not a guarantee of
continuous availability: successful snapshots do not cover intervals between runs.
A sufficient window still leaves `qualified_research_ready` and
`promotion_authorized` false. Review failure causes, timing, source freshness and
coverage requirements for the intended operating cadence separately.

Enumeration is bounded to 500 entries by default, configurable from 1 through
1,000. Each assessment is limited to 1 MiB. Extra entries explicitly mark the
summary truncated and invalid; no partial subset can pass the window gate. Split
large histories through an explicit retention process rather than raising the
bound indefinitely. Symlink path components, symlink records, malformed JSON,
duplicate object keys, nonfinite numbers and unsafe run identifiers are rejected.

## CLI and continued observation

```sh
quant-task shadow-history --root /absolute/external/shadow-runs \
  --expected-config-sha256 APPROVED_CONFIG_SHA256
```

`shadow-check` now records UTC `observed_at` and monotonic measured
`duration_seconds`. After configuration validation, binding or execution failures
are retained as failed observations with a safe `failure_phase`; invalid
configuration is rejected before any attempt/output. A failed assessment is a
valid command response, so inspect `status` rather than treating exit zero as
readiness. Crashed or interrupted partial directories make history invalid.

For continued observation, use a dedicated stable installed release and an
explicitly approved configuration pin, with output in a separate data namespace.
Prepare a user service/timer for review; do not point it at a temporary worktree
or replace an existing authoritative schedule. Changing a source pin starts a
new cohort. Retain failures and distinguish source staleness from command failure.
This increment runs a bounded manual acceptance and **does not install or enable
a timer**. Continuous observation and production migration remain separate
operational decisions. Local outbox receipts remain the notification boundary.
