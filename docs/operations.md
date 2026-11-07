# Operation and recovery

Run one `quant-task ... run` process per coordinator database. A nonblocking OS
file lock fences each scheduler pass across processes. Runtime's own scheduler
continues to own its database and workers. Configure queued Runtime tasks with
`queue=true` and run its existing scheduler independently; this coordinator never
starts `serve`, changes concurrency or recovers Runtime leases implicitly.

## Lost responses and crashes

A dispatch record is committed before an owner command. Subsequent ticks use the
same Runtime key/job ID. If lookup cannot prove a job exists, the step stays
`UNKNOWN`; the coordinator never submits again when lookup cannot establish an existing job.
When lookup proves an existing job, the adapter replays the exact plan-bound request to ask Runtime to verify its request fingerprint and requires the same job ID. This idempotent replay does not start another execution; a conflicting request is rejected. Published result hashes must also match the approved request. This also covers a crash immediately before the first submission actually ran.
It deliberately trades automatic progress for duplicate-effect safety. An operator
must inspect the owner, preserve the old evidence, and deliberately create a new
workflow/request key only when a new execution is intended.

A completed Runtime result is reread through `result`, which verifies published
hashes before dependent steps run. Research results retain the original proposal,
experiment and runtime identities in the owner. No completed job implies PIT,
economic validity or permission to promote.

## Cancellation and blockers

`cancel` records intent; a scheduler tick performs owner cancellation. Waiting
steps stop immediately. Already completed steps and their evidence are retained.
Runtime cancellation is reconciled using its original job identity. A mutation
already in flight when cancellation is requested may reach the owner; subsequent
polling reconciles and cancels it. Do not interpret cancellation as instant process
termination.

The Research CLI has no general cancellation command, so cancellation of an active
Research step remains `UNKNOWN` with `OWNER_CANCELLATION_REQUIRES_OPERATOR` until an
operator handles it through owner tools. The coordinator does not invent that API.
When input/code bindings change, restore and verify the approved immutable release
before reconciliation. The coordinator will not dispatch a never-started blocked
step automatically. Do not edit stored approvals or task rows to force progress.

## Storage and execution

Use `DATA_ROOT/<owning-project>/` for retained databases and generated reports,
`CONFIG_ROOT/projects/quant-task-orchestrator/` for private configuration. Plans
contain private locators; protect them as configuration, not public artifacts.
Temporary validation uses unique directories under the system temporary root.
Back up SQLite with its backup API or quiesce writers; copying only a live main
file can lose WAL transactions. Retain owner requests, immutable artifacts and
release identities together. Do not replace another task's `latest` pointer.

Owner calls time out after 30 seconds. Timeout is uncertain and never authorizes
resubmission. File-backed capture bounds in-memory response reads to 1 MiB; trusted
CLIs and OS disk quotas must bound temporary-file growth. No arbitrary user shell,
model session or resource-intensive computation executes in the coordinator.

## Future production adoption

No cron or systemd timer was changed by this release. Before adopting a workflow,
register one owner at a time and validate against a separate synthetic database.
Avoid two scheduling systems submitting the same authorized work. Real PIT evidence,
research semantic mapping and economic audits remain owner prerequisites.
