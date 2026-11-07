"""Explicit local event polling and notification receipts; no external transport.

Inputs remain in place for audit. The receipt journal quarantines rejected fingerprints.
A crash between Store.hint and receipt commit replays the original event, whose Store
transaction already enforces event identity. Operational failures are retried, not rejected.
"""

import hashlib
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

MAX_EVENT_BYTES = 16384
MAX_FILES = 500


def safe_path(path):
    """Reject symlink components, including broken links, before local writes."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError("SYMLINK_PATH")
    return path


@contextmanager
def journal(path):
    path = safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript("""
        PRAGMA synchronous=FULL;
        CREATE TABLE IF NOT EXISTS receipts (
            fingerprint TEXT PRIMARY KEY, disposition TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS outbox (
            id TEXT PRIMARY KEY, body TEXT NOT NULL, acked INTEGER NOT NULL DEFAULT 0);
    """)
    try:
        with db:
            yield db
    finally:
        db.close()


def consume_once(store, inbox, ledger):
    inbox = safe_path(inbox)
    if not inbox.is_dir():
        raise ValueError("INBOX_NOT_DIRECTORY")
    result = dict(accepted=0, duplicates=0, rejected=0, deferred=0)
    with journal(ledger) as db:
        processed = 0
        # Completed receipts do not spend the pending-event budget. Enumeration and
        # bounded reads may traverse the full directory, but memory stays bounded.
        with os.scandir(inbox) as entries:
            for entry in entries:
                if not entry.name.endswith(".json"):
                    continue
                raw = None
                try:
                    fd = os.open(entry.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                    with os.fdopen(fd, "rb") as source:
                        info = os.fstat(source.fileno())
                        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_EVENT_BYTES:
                            raise ValueError("INVALID_FILE")
                        raw = source.read(MAX_EVENT_BYTES + 1)
                    if len(raw) > MAX_EVENT_BYTES:
                        raise ValueError("EVENT_TOO_LARGE")
                    fingerprint = hashlib.sha256(raw).hexdigest()
                except (ValueError, OSError):
                    raw = None
                    try:
                        info = entry.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        continue  # A producer removed the file; no event was consumed.
                    identity = f"{entry.name}:{info.st_ino}:{info.st_mtime_ns}:{info.st_size}"
                    fingerprint = hashlib.sha256(identity.encode()).hexdigest()
                old = db.execute(
                    "SELECT disposition FROM receipts WHERE fingerprint=?", (fingerprint,)
                ).fetchone()
                if old:
                    result["duplicates" if old[0] == "accepted" else "rejected"] += 1
                    continue
                if processed >= MAX_FILES:
                    result["deferred"] += 1
                    break
                processed += 1
                try:
                    if raw is None:
                        raise ValueError("INVALID_FILE")

                    def unique_pairs(pairs):
                        value = {}
                        for key, item in pairs:
                            if key in value:
                                raise ValueError("DUPLICATE_JSON_KEY")
                            value[key] = item
                        return value

                    event = json.loads(raw, object_pairs_hook=unique_pairs)
                    if not isinstance(event, dict):
                        raise ValueError("INVALID_EVENT")
                    receipt = store.hint(event)
                except (ValueError, TypeError, KeyError, UnicodeError):
                    db.execute(
                        "INSERT OR IGNORE INTO receipts VALUES (?,?)", (fingerprint, "rejected")
                    )
                    db.commit()
                    result["rejected"] += 1
                    continue
                db.execute("INSERT OR IGNORE INTO receipts VALUES (?,?)", (fingerprint, "accepted"))
                db.commit()
                result["accepted" if receipt["created"] else "duplicates"] += 1
    return result


def enqueue_notification(ledger, view, action_signature):
    if not isinstance(action_signature, str) or not 1 <= len(action_signature) <= 200:
        raise ValueError("INVALID_ACTION_SIGNATURE")
    body = {key: view[key] for key in ("workflow_id", "status", "plan_sha256")}
    body["action_signature"] = action_signature
    # Include recovery-relevant state without arbitrary titles, errors or owner payloads.
    body["steps"] = [
        {key: step.get(key) for key in ("id", "status", "evidence_status")}
        for step in view.get("steps", [])
    ]
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
    if len(payload.encode()) > 65536:
        raise ValueError("NOTIFICATION_TOO_LARGE")
    nid = hashlib.sha256(payload.encode()).hexdigest()
    with journal(ledger) as db:
        db.execute("INSERT OR IGNORE INTO outbox(id,body) VALUES (?,?)", (nid, payload))
    return {"notification_id": nid, "transport": "local_outbox"}


def list_notifications(ledger, *, include_acked=False):
    with journal(ledger) as db:
        rows = db.execute(
            "SELECT * FROM outbox WHERE acked=0 OR ? ORDER BY rowid LIMIT 500",
            (bool(include_acked),),
        )
        return [
            dict(
                notification_id=row["id"],
                acknowledged=bool(row["acked"]),
                **json.loads(row["body"]),
            )
            for row in rows
        ]


def acknowledge_notification(ledger, notification_id):
    with journal(ledger) as db:
        updated = db.execute("UPDATE outbox SET acked=1 WHERE id=?", (notification_id,))
        if not updated.rowcount:
            raise ValueError("NOTIFICATION_NOT_FOUND")
    return {"notification_id": notification_id, "acknowledged": True}
