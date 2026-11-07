"""Offline restore, local notification receipts and scheduler migration preflight.

This module never executes a scheduler cutover or selects an external transport.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from .event_inbox import journal, safe_path

# Required contract columns; additive schema changes remain restorable.
_SCHEMA = {
    "workflows": {"id", "key", "hash", "plan", "approval", "cancelled", "created", "updated"},
    "steps": {"workflow_id", "id", "status", "owner_id", "evidence", "error", "updated"},
    "observations": {"workflow_id", "step_id", "snapshot", "recorded_at"},
    "execution_snapshots": {"workflow_id", "step_id", "snapshot", "recorded_at"},
    "step_telemetry": {
        "workflow_id",
        "step_id",
        "owner_calls",
        "owner_errors",
        "owner_call_wall_seconds",
    },
    "transitions": {"seq", "workflow_id", "step_id", "status", "created"},
    "workflow_signals": {"event_id", "workflow_id", "source", "type"},
    "events": {"seq", "workflow_id", "event_id", "hash", "type", "step_id", "created"},
}


def restore_database(source, destination, sha256):
    """Restore a pinned backup into a new path only, without opening the source writable."""
    source, destination = safe_path(source), safe_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.exists():
        raise FileExistsError("RESTORE_TARGET_EXISTS")
    fd, name = tempfile.mkstemp(prefix=".restore-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as output, source.open("rb") as original:
            shutil.copyfileobj(original, output)
            output.flush()
            os.fsync(output.fileno())
        with temporary.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != sha256:
            raise ValueError("BACKUP_DIGEST_MISMATCH")
        with closing(sqlite3.connect(temporary.as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise ValueError("RESTORE_INTEGRITY_FAILED")
            for table, required in _SCHEMA.items():
                columns = {row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}
                if not required <= columns:
                    raise ValueError("RESTORE_SCHEMA_MISMATCH")
        # Atomic exclusive publication: unlike rename this cannot replace a racing writer.
        os.link(temporary, destination)
        return dict(
            path=str(destination), sha256=actual, integrity="ok", schema="quant.workflow_store.v1"
        )
    finally:
        temporary.unlink(missing_ok=True)


def _receipt(value, notification_id):
    if (
        not isinstance(value, dict)
        or value.get("notification_id") != notification_id
        or not isinstance(value.get("receipt_id"), str)
        or not value["receipt_id"]
    ):
        raise ValueError("INVALID_TRANSPORT_RECEIPT")
    return value


def dispatch_notification(ledger, notification_id, *, peer=None, dry_run=True):
    """Send only to an explicitly injected local peer; reconcile uncertain sends.

    Peer lookup(id) returns a receipt or None; send(id, body) must deduplicate by id.
    An uncertain attempt is never resent automatically, even if lookup returns None.
    """
    with journal(ledger) as db:
        row = db.execute("SELECT body FROM outbox WHERE id=?", (notification_id,)).fetchone()
        if row is None:
            raise ValueError("NOTIFICATION_NOT_FOUND")
        if dry_run:
            return dict(notification_id=notification_id, status="dry_run")
        if peer is None or getattr(peer, "local_only", False) is not True:
            raise ValueError("LOCAL_PEER_REQUIRED")
        db.execute(
            "CREATE TABLE IF NOT EXISTS transport_receipts "
            "(id TEXT PRIMARY KEY, status TEXT NOT NULL, receipt TEXT)"
        )
        # Reserve before any transport call, including lookup. Concurrent dispatchers
        # may reconcile but cannot acquire a second initial send.
        inserted = db.execute(
            "INSERT OR IGNORE INTO transport_receipts VALUES (?, ?, NULL)",
            (notification_id, "uncertain"),
        ).rowcount
        db.commit()
        old = db.execute(
            "SELECT status,receipt FROM transport_receipts WHERE id=?", (notification_id,)
        ).fetchone()
        if old["status"] == "delivered":
            return dict(
                notification_id=notification_id,
                status="delivered",
                receipt=json.loads(old["receipt"]),
            )
        try:
            receipt = peer.lookup(notification_id)
            if receipt is None and inserted:
                receipt = peer.send(notification_id, json.loads(row["body"]))
            if receipt is None:
                return dict(notification_id=notification_id, status="uncertain")
            receipt = _receipt(receipt, notification_id)
        except (TimeoutError, OSError, ValueError):
            return dict(notification_id=notification_id, status="uncertain")
        db.execute(
            "UPDATE transport_receipts SET status=?,receipt=? WHERE id=?",
            ("delivered", json.dumps(receipt, sort_keys=True), notification_id),
        )
        return dict(notification_id=notification_id, status="delivered", receipt=receipt)


def scheduler_migration_plan(old_owner, new_owner, *, old_active, new_active):
    """Check explicit ownership observations; produce a proposal, never a cutover."""
    if (
        not isinstance(old_owner, str)
        or not old_owner.strip()
        or not isinstance(new_owner, str)
        or not new_owner.strip()
        or old_owner == new_owner
        or type(old_active) is not bool
        or type(new_active) is not bool
    ):
        raise ValueError("INVALID_SCHEDULER_OWNERSHIP")
    blockers = []
    if old_active and new_active:
        blockers.append("DUAL_ACTIVE_OWNERS")
    if not old_active:
        blockers.append("OLD_OWNER_NOT_ACTIVE")
    if new_active:
        blockers.append("NEW_OWNER_ALREADY_ACTIVE")
    return dict(
        schema="quant.scheduler_migration_plan.v1",
        old_owner=old_owner,
        new_owner=new_owner,
        old_active=old_active,
        new_active=new_active,
        ready=not blockers,
        blockers=blockers,
        cutover_executed=False,
        actions=[
            "capture_old_schedule",
            "verify_new_shadow",
            "disable_old_owner",
            "verify_old_inactive",
            "enable_new_owner",
            "verify_single_owner",
        ],
    )


def storage_assessment(directory, *, minimum_free_bytes=1_073_741_824):
    """Read available storage; this probe does not enforce quotas or delete files."""
    directory = safe_path(directory)
    if not directory.is_dir() or type(minimum_free_bytes) is not int or minimum_free_bytes < 0:
        raise ValueError("INVALID_STORAGE_PROBE")
    usage = shutil.disk_usage(directory)
    ready = usage.free >= minimum_free_bytes
    return dict(
        schema="quant.storage_assessment.v1",
        ready=ready,
        code="OK" if ready else "INSUFFICIENT_FREE_SPACE",
        total_bytes=usage.total,
        free_bytes=usage.free,
        minimum_free_bytes=minimum_free_bytes,
        mutations=False,
    )
