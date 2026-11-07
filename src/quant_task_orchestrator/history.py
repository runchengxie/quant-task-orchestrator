"""Pinned, sanitized owner history projections; Research remains authoritative."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA = "quant.research_history.v1"
FIELDS = {
    "record_id",
    "source_kind",
    "status",
    "stage",
    "decision",
    "classification",
    "evidence_stage",
    "provenance",
    "evidence_handles",
    "topic_tags",
    "reason_codes",
    "revisit_conditions",
}
FILTERS = {
    "source_kind",
    "status",
    "stage",
    "decision",
    "classification",
    "evidence_stage",
    "topic_tags",
    "reason_codes",
    "revisit_conditions",
}


def _hex(value, size):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{" + str(size) + "}", value)


def _load(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_HISTORY_JSON_KEY")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("INVALID_HISTORY_JSON_CONSTANT")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("INVALID_HISTORY_JSON") from exc


def validate_history(value):
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "owner",
        "source_revision",
        "source_id",
        "records",
    }:
        raise ValueError("INVALID_HISTORY_PROJECTION")
    if (
        value["schema"] != SCHEMA
        or value["owner"] != "quant-research"
        or not _hex(value["source_revision"], 40)
    ):
        raise ValueError("INVALID_HISTORY_OWNER")
    if not isinstance(value["source_id"], str) or not re.fullmatch(
        r"[A-Za-z0-9_.:-]{1,100}", value["source_id"]
    ):
        raise ValueError("INVALID_HISTORY_SOURCE")
    if not isinstance(value["records"], list) or len(value["records"]) > 100000:
        raise ValueError("INVALID_HISTORY_RECORDS")
    identities = set()
    for row in value["records"]:
        if not isinstance(row, dict) or set(row) != FIELDS or not _hex(row["record_id"], 64):
            raise ValueError("INVALID_HISTORY_RECORD")
        if row["record_id"] in identities:
            raise ValueError("DUPLICATE_HISTORY_RECORD")
        identities.add(row["record_id"])
        for field in ("status", "stage", "decision"):
            token = row[field]
            if token is not None and (
                not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", token)
            ):
                raise ValueError("INVALID_HISTORY_TOKEN")
        if not isinstance(row["source_kind"], str) or row["source_kind"] not in {
            "experiment",
            "campaign",
        }:
            raise ValueError("INVALID_HISTORY_KIND")
        if not isinstance(row["classification"], str) or row["classification"] not in {
            "research_conclusion",
            "operational_failure",
            "unclassified",
        }:
            raise ValueError("INVALID_HISTORY_CLASSIFICATION")
        if not isinstance(row["evidence_stage"], str) or row["evidence_stage"] not in {
            "owner_recorded",
            "not_verified",
        }:
            raise ValueError("INVALID_HISTORY_STAGE")
        provenance = row["provenance"]
        if not isinstance(provenance, dict) or set(provenance) != {
            "source_revision",
            "source_database_sha256",
            "annotations_sha256",
            "owner_source_revision",
            "dataset_fingerprint_sha256",
        }:
            raise ValueError("INVALID_HISTORY_PROVENANCE")
        if provenance["source_revision"] != value["source_revision"] or not _hex(
            provenance["source_database_sha256"], 64
        ):
            raise ValueError("INVALID_HISTORY_PROVENANCE")
        if provenance["annotations_sha256"] is not None and not _hex(
            provenance["annotations_sha256"], 64
        ):
            raise ValueError("INVALID_HISTORY_PROVENANCE")
        for key, size in (("owner_source_revision", 40), ("dataset_fingerprint_sha256", 64)):
            if provenance[key] is not None and not _hex(provenance[key], size):
                raise ValueError("INVALID_HISTORY_PROVENANCE")
        for key in ("topic_tags", "reason_codes", "revisit_conditions"):
            tags = row[key]
            if (
                not isinstance(tags, list)
                or len(tags) > 20
                or any(
                    not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", tag)
                    for tag in tags
                )
            ):
                raise ValueError("INVALID_HISTORY_ANNOTATIONS")
        handles = row["evidence_handles"]
        if (
            not isinstance(handles, list)
            or len(handles) > 1000
            or any(
                not isinstance(h, str) or not re.fullmatch(r"artifact://sha256/[0-9a-f]{64}", h)
                for h in handles
            )
        ):
            raise ValueError("INVALID_HISTORY_HANDLES")
    return value


def install_history(store, path, sha):
    """Import an explicitly selected, externally pinned owner export atomically."""
    if store.readonly:
        raise ValueError("READ_ONLY_STORE")
    if not _hex(sha, 64):
        raise ValueError("INVALID_HISTORY_PIN")
    with Path(path).open("rb") as stream:
        raw = stream.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != sha:
        raise ValueError("HISTORY_DIGEST_MISMATCH")
    value = validate_history(_load(raw))
    with store.db:
        store.db.execute(
            "INSERT OR IGNORE INTO research_history_snapshots(snapshot_sha256,source_revision,payload) VALUES(?,?,?)",
            (sha, value["source_revision"], raw.decode("utf-8")),
        )
    return {
        "snapshot_sha256": sha,
        "source_id": value["source_id"],
        "source_revision": value["source_revision"],
        "record_count": len(value["records"]),
    }


def search_history(store, *, snapshot_sha256=None, q="", limit=50, offset=0, **filters):
    """Read only explicitly imported projections; never open owner source files."""
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise ValueError("INVALID_HISTORY_PAGE")
    if not isinstance(q, str) or len(q) > 256 or set(filters) - FILTERS:
        raise ValueError("INVALID_HISTORY_FILTER")
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", value)
        for value in filters.values()
    ):
        raise ValueError("INVALID_HISTORY_FILTER")
    if snapshot_sha256 is not None and not _hex(snapshot_sha256, 64):
        raise ValueError("INVALID_HISTORY_PIN")
    if not store.db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='research_history_snapshots'"
    ).fetchone():
        return {
            "schema": SCHEMA,
            "snapshot_sha256": snapshot_sha256,
            "records": [],
            "total": 0,
            "next_offset": None,
        }
    if snapshot_sha256 is None:
        rows = store.db.execute(
            "SELECT snapshot_sha256,payload FROM research_history_snapshots ORDER BY rowid DESC LIMIT 1"
        ).fetchall()
    else:
        rows = store.db.execute(
            "SELECT snapshot_sha256,payload FROM research_history_snapshots WHERE snapshot_sha256=?",
            (snapshot_sha256,),
        ).fetchall()
    if not rows:
        return {
            "schema": SCHEMA,
            "snapshot_sha256": snapshot_sha256,
            "records": [],
            "total": 0,
            "next_offset": None,
        }
    sha, payload = rows[0]
    if hashlib.sha256(payload.encode("utf-8")).hexdigest() != sha:
        raise ValueError("HISTORY_DIGEST_MISMATCH")
    value = validate_history(_load(payload))
    records = [
        row
        for row in value["records"]
        if all(
            (wanted in row[key] if isinstance(row[key], list) else row[key] == wanted)
            for key, wanted in filters.items()
        )
        and q.casefold() in json.dumps(row, sort_keys=True).casefold()
    ]
    page = records[offset : offset + limit]
    return {
        "schema": SCHEMA,
        "snapshot_sha256": sha,
        "source_id": value["source_id"],
        "records": page,
        "total": len(records),
        "next_offset": offset + limit if offset + limit < len(records) else None,
    }
