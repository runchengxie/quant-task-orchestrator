"""Explicit imports and integrity-checked read-only financial result queries."""

import hashlib
import re
import sqlite3

from .economic_results import compare_results, parse_result, read_result_bytes

MAX_BYTES = 1_048_576


def _pin(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("INVALID_ECONOMIC_CACHE_PIN")
    return value


def _exists(store):
    return (
        store.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='economic_result_snapshots'"
        ).fetchone()
        is not None
    )


def _decode(row):
    sha, size, body = row
    _pin(sha)
    if size > MAX_BYTES or not isinstance(body, bytes) or hashlib.sha256(body).hexdigest() != sha:
        raise ValueError("ECONOMIC_CACHE_INTEGRITY_FAILED")
    return {"snapshot_sha256": sha, "result": parse_result(body)}


def _select():
    # Avoid materializing oversized/corrupted cache payloads before checking length.
    return "SELECT snapshot_sha256,length(payload),CASE WHEN length(payload)<=1048576 THEN payload ELSE NULL END FROM economic_result_snapshots"


def import_result(store, path, sha):
    if store.readonly:
        raise ValueError("READ_ONLY_STORE")
    _pin(sha)
    body = read_result_bytes(path, sha)
    value = parse_result(body)
    with store.db:
        store.db.execute(
            "INSERT OR IGNORE INTO economic_result_snapshots(snapshot_sha256,payload) VALUES(?,?)",
            (sha, sqlite3.Binary(body)),
        )
        _decode(store.db.execute(_select() + " WHERE snapshot_sha256=?", (sha,)).fetchone())
    return {
        "schema": "quant.economic_result_import.v1",
        "snapshot_sha256": sha,
        "result_id": value["result_id"],
        "provenance_verified": False,
    }


def list_results(store, *, limit=100, offset=0):
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise ValueError("INVALID_ECONOMIC_RESULT_PAGE")
    total, rows = 0, []
    if _exists(store):
        total = store.db.execute("SELECT COUNT(*) FROM economic_result_snapshots").fetchone()[0]
        rows = store.db.execute(
            _select() + " ORDER BY rowid DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    return {
        "schema": "quant.economic_result_list.v1",
        "results": [_decode(row) for row in rows],
        "total": total,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total else None,
        "provenance_verified": False,
    }


def compare_cached(store, before, after):
    _pin(before)
    _pin(after)
    if not _exists(store):
        raise ValueError("ECONOMIC_RESULT_NOT_IMPORTED")
    values = []
    # One read snapshot preserves the pair even if another process imports receipts.
    store.db.execute("SAVEPOINT economic_comparison")
    try:
        for pin in (before, after):
            row = store.db.execute(_select() + " WHERE snapshot_sha256=?", (pin,)).fetchone()
            if row is None:
                raise ValueError("ECONOMIC_RESULT_NOT_IMPORTED")
            values.append(_decode(row)["result"])
        result = compare_results(*values)
        result["input_pins"] = {"before_sha256": before, "after_sha256": after}
        return result
    finally:
        store.db.execute("RELEASE economic_comparison")
