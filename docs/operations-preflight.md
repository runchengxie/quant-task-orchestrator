# Operations preflight

[简体中文](operations-preflight.zh-CN.md)

These Python interfaces are offline or local-only. They do not install services,
change schedules, delete retained data, or contact human recipients.

`ops.restore_database(source, destination, sha256)` verifies the caller-pinned
backup checksum, SQLite integrity and required workflow-store columns before
publishing a new file atomically. The source should be the completed output of
`deployment.backup_database`, rather than a live database with WAL sidecars.
The target must not exist; restore never replaces an active database. Keep the
backup and its externally recorded checksum together in the project data root.
This is a recovery rehearsal; production activation remains a separate operation.

`ops.dispatch_notification(ledger, notification_id, peer=None, dry_run=True)`
previews by default. Explicit delivery requires an injected local peer with
`local_only = True`, `lookup(notification_id)` and
`send(notification_id, body)`. Both methods return either a receipt with matching
`notification_id` and a nonempty `receipt_id`, or (lookup only) `None`.
The peer must deduplicate by notification ID. Delivery receipts are separate
from a user's acknowledgement in the original outbox.

The journal commits `uncertain` before contacting the peer. A lost response or
crash therefore causes subsequent dispatches to query the same notification ID;
they never automatically resend an uncertain attempt. A missing reconciliation
receipt remains uncertain for operator investigation. This intentionally trades
automatic retry for duplicate prevention. No network transport is included.

`ops.scheduler_migration_plan(old_owner, new_owner, old_active=..., new_active=...)`
checks explicitly supplied ownership observations and returns a proposed action
sequence. `ready` means the supplied old owner is active and the new owner is
inactive; it does not certify production safety or fresh observation evidence.
Dual-active ownership blocks readiness. `cutover_executed` is always false.
Recheck real scheduler inventory, shadow results and rollback readiness before
separately authorizing any migration. Running this function cannot perform one.
