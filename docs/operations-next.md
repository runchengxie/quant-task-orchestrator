# Local events, releases and locked Skills

These helpers make explicit local operations inspectable. They do not activate services,
run imported Skill code, grant permissions, submit owner work or contact messaging services.
Use configured absolute CODE_ROOT, DATA_ROOT and CONFIG_ROOT values; keep journal files,
backups and releases outside task worktrees. Only synthetic temporary files are used by tests.

## Event inbox and local notification outbox

`event_inbox.consume_once(store, inbox, ledger)` polls only the named directory. Producers
must publish a complete UTF-8 JSON file by atomic rename from a temporary non-`.json` name.
The envelope is exactly the existing `quant.workflow_event.v1`: `schema`, `event_id`,
`workflow_id`, `source`, `type`. Preserve the original publisher identity and event ID.
The Store independently checks workflow existence, allowed event types and immutable event
identity. A hint never approves a workflow; reconciliation still revalidates its owner.

One poll processes at most 500 pending fingerprints and accepts files up to 16 KiB.
Already completed receipts are skipped before applying that budget, so retained older files
cannot starve new events. Enumeration and bounded file reads may traverse the directory;
memory usage stays bounded. Duplicate
JSON keys, non-regular files, symlinks and malformed envelopes are rejected. Use directories
owned by the operator, inaccessible to untrusted local writers: filesystem path preflight
is not a sandbox against a concurrent privileged directory replacement. Unknown non-JSON
files remain untouched. Inputs remain in place for audit; archive old inputs explicitly
when appropriate for retention and scan cost. The receipt journal is a local SQLite
database with full synchronous commits. Rejected fingerprints are quarantine receipts;
raw rejected payloads, names and exception details are never copied into output. The result
contains only accepted/duplicate/rejected/deferred counts.

The Store transaction and journal transaction are separate. If the process dies after the
Store commits, the next poll calls `Store.hint` with the exact same envelope; the Store's
unique event ID and content hash prevent a second effect. A different payload reusing an
ID is quarantined. SQLite operational errors propagate for retry. No scheduler runs here.

`enqueue_notification(ledger, view, action_signature)` records a local outbox item using a
hash of workflow ID, status, frozen plan digest, relevant step state and action signature.
It deliberately omits arbitrary titles, owner responses and error text. Repeated calls are
idempotent even after restart and after acknowledgement. `list_notifications(ledger)`
returns up to 500 pending entries; `acknowledge_notification(ledger, notification_id)` marks
local processing complete. No email, chat, webhook or other external transport is configured.
An external sender would need its own authorization and remote delivery idempotency contract.

## Stable private release proposal

`deployment.stage_release(wheel, sha256, revision, releases)` checks a local wheel digest and
40-character source commit, then reserves a fresh `<revision>-<digest-prefix>` directory
containing the wheel and `release.json`. It never replaces existing releases. The caller
must independently verify that the wheel was built from the reviewed merged source commit;
a wheel digest alone cannot prove build provenance. Interrupted staging may leave a reserved
incomplete directory; inspect it rather than overwrite or activate it. No package manager,
network access or service manager is invoked. A manifest says `installed=false` and
`activated=false` until a separate authorized operational step installs and activates it.

`service_unit(release, data_root, config_root, port=8787)` returns a systemd user-unit proposal.
The selected stable release must already have `venv/bin/quant-task`. Install a verified wheel
and its approved dependencies into that release in a separately reviewed deployment step.
The GUI binds IPv4 loopback, reads
`DATA_ROOT/quant/quant-task-orchestrator/state.sqlite`, and loads a bearer token from
`CONFIG_ROOT/projects/quant-task-orchestrator/gui.token`. Token files are private operator
configuration; never put token values into the unit or repository. The service has a read-only
filesystem policy and exposes the read-only API. It does not start workers or timers.
`examples/quant-task.service` documents the same layout with placeholders.

Before a release change, `backup_database(source, destination)` creates a new owner-only
SQLite backup using SQLite's online backup interface, checks database integrity and returns
a SHA-256 receipt. It refuses to overwrite an existing backup. Restore testing and activation
remain explicit operator actions. `verify_health(url, token=...)` probes an explicit loopback
HTTP JSON endpoint with a five-second timeout, size limit and redirects disabled. Use a
explicit `/v1/health` endpoint. Verification requires the exact
`quant.workbench_health.v1` schema, `status=ok`, `mode=read_only` and a Boolean
`authentication_required` field; an unrelated JSON service fails. This proves workbench
availability, not owner conformance, worker availability or research validity.

## Locked Skill distribution

`skill_install.install_skill(repo, revision, path, sha256, destination, *, owner_repo,
permissions, input_contract, output_contract)` extracts exactly one regular, non-executable
`SKILL.md` Git blob at an exact commit from a local repository, validates its UTF-8 content
and SHA-256, and installs inert read-only text under `<destination>/<sha256>/SKILL.md`.
The destination must be external to the source repository. Paths cannot traverse outside
the tree, source blobs cannot be symlinks, and destination path components cannot be symlinks.
An existing digest directory causes an error, even if its bytes appear identical.

`receipt.json` records the owner, commit, source path, digest, declared permissions and input
and output contracts. These permissions are declarations, not grants. Only the selected
Skill text is distributed: referenced support files, executables and dependencies are not
installed, and `support_files_installed=false` makes that limit explicit. Review those
references before enabling a Skill in any agent. No imported code is executed and no package
manager or network download is used. The owner identifier is a pinned declaration supplied
by the caller, not a proof that a local Git remote belongs to that owner.

## CLI operations

Only commands that inspect or mutate workflow state require global `--database`. The
commands below preserve the same explicit paths and permissions as the Python helpers.
All output is JSON; errors return a sanitized error code. Replace root variables with
configured absolute paths and choose task-specific temporary paths for validation.

Consume a single inbox batch, or consume before every scheduler iteration:

```sh
quant-task --database "$DATA_ROOT/quant/quant-task-orchestrator/state.sqlite" inbox \
  --inbox "$DATA_ROOT/quant/quant-task-orchestrator/inbox" \
  --ledger "$DATA_ROOT/quant/quant-task-orchestrator/operations.sqlite"
quant-task --database "$DATA_ROOT/quant/quant-task-orchestrator/state.sqlite" run --once \
  --inbox "$DATA_ROOT/quant/quant-task-orchestrator/inbox" \
  --ledger "$DATA_ROOT/quant/quant-task-orchestrator/operations.sqlite"
```

`run --inbox` and `--ledger` must be supplied together. Without them the scheduler retains
its existing behavior. A one-shot run returns its latest inbox summary alongside workflows.
Inbox consumption does not automatically generate notifications. Enqueue a selected frozen
workflow view explicitly, then inspect and acknowledge local outbox entries:

```sh
quant-task --database "$DATABASE" outbox-enqueue WORKFLOW_ID \
  --ledger "$LEDGER" --action-signature inspect
quant-task outbox-list --ledger "$LEDGER"
quant-task outbox-ack NOTIFICATION_ID --ledger "$LEDGER"
quant-task outbox-list --ledger "$LEDGER" --include-acked
```

These commands only write or read local receipts; acknowledgement sends nothing externally.
`outbox-enqueue` opens the workflow database read-only. `outbox-list` and `outbox-ack` require
only the ledger.

Select exactly one catalog entry by ID from the private orchestrator configuration:

```sh
quant-task skill-install --config "$CONFIG_ROOT/projects/quant-task-orchestrator/config.json" \
  --skill-id reviewed-skill --destination "$DATA_ROOT/quant/quant-task-orchestrator/installed-skills"
```

The entry must contain all existing locked catalog fields: `id`, `owner_repo`, absolute local
`source`, exact `revision`, `path`, `sha256`, `permissions`, `input_contract`, `output_contract`.
Missing or duplicate selected IDs fail; the installer validates the commit and content again.
This installs inert text only and does not change an agent's enabled Skills.

Prepare a stable release and service proposal using reviewed artifact values:

```sh
quant-task release-stage --wheel "$WHEEL" --sha256 "$WHEEL_SHA256" \
  --revision "$MERGED_COMMIT" --releases "$CODE_ROOT/production/quant-task-orchestrator/releases"
quant-task service-unit --release "$RELEASE" --data-root "$DATA_ROOT" \
  --config-root "$CONFIG_ROOT" --port 8787 --output "$UNIT_PROPOSAL"
quant-task backup --source "$DATABASE" --destination "$NEW_BACKUP"
quant-task health --url http://127.0.0.1:8787/v1/health \
  --token-file "$CONFIG_ROOT/projects/quant-task-orchestrator/gui.token"
```

`service-unit --output` creates a new file and refuses replacement; without it the generated
unit appears in the JSON `unit` field. The command does not install or start the proposal.
`health` reads a private token file using the same owner-only permission checks as the API;
no token value is accepted as a command-line argument or included in output.
