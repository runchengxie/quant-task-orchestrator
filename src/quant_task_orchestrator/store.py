"""Durable workflow state and explicit, allowlisted public projections."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .contracts import canonical, digest, exact, identifier

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}
STEP_STATES = TERMINAL | {"WAITING", "DISPATCHING", "RUNNING", "UNKNOWN", "BLOCKED"}


def now():
    return datetime.now(UTC).isoformat()


class Store:
    def __init__(self, path, *, readonly=False):
        self.path = Path(path).absolute()
        self.readonly = readonly
        if readonly:
            self.db = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True, timeout=10)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(self.path, timeout=10)
            self.db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS workflows(
                    id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, hash TEXT NOT NULL,
                    plan TEXT NOT NULL, approval TEXT, cancelled INTEGER NOT NULL DEFAULT 0,
                    created TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS steps(
                    workflow_id TEXT NOT NULL, id TEXT NOT NULL, status TEXT NOT NULL,
                    owner_id TEXT, evidence TEXT NOT NULL DEFAULT 'NOT_VERIFIED', error TEXT,
                    updated TEXT NOT NULL, PRIMARY KEY(workflow_id,id));
                CREATE TABLE IF NOT EXISTS events(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL,
                    event_id TEXT UNIQUE, hash TEXT, type TEXT NOT NULL, step_id TEXT,
                    created TEXT NOT NULL);
            """)
        self.db.row_factory = sqlite3.Row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        self.db.close()

    def _event(self, wid, event_type, sid=None):
        self.db.execute(
            "INSERT INTO events(workflow_id,type,step_id,created) VALUES(?,?,?,?)",
            (wid, event_type, sid, now()),
        )
        self.db.execute("UPDATE workflows SET updated=? WHERE id=?", (now(), wid))

    def record(self, wid):
        row = self.db.execute("SELECT * FROM workflows WHERE id=?", (wid,)).fetchone()
        if row is None:
            raise ValueError("WORKFLOW_NOT_FOUND")
        return dict(row)

    def plan(self, wid):
        return json.loads(self.record(wid)["plan"])

    def submit(self, plan):
        body = {k: v for k, v in plan.items() if k != "plan_sha256"}
        if plan.get("schema") != "quant.workflow_plan.v1" or digest(body) != plan.get(
            "plan_sha256"
        ):
            raise ValueError("INVALID_PLAN")
        key, fingerprint = identifier(plan["workflow"]["idempotency_key"]), plan["plan_sha256"]
        with self.db:
            # Take a write reservation before reading the uniqueness decision.
            self.db.execute("BEGIN IMMEDIATE")
            old = self.db.execute("SELECT id,hash FROM workflows WHERE key=?", (key,)).fetchone()
            if old:
                if old["hash"] != fingerprint:
                    raise ValueError("WORKFLOW_IDEMPOTENCY_CONFLICT")
                return {"workflow_id": old["id"], "created": False, "plan_sha256": fingerprint}
            wid = str(uuid.uuid4())
            timestamp = now()
            self.db.execute(
                "INSERT INTO workflows(id,key,hash,plan,created,updated) VALUES(?,?,?,?,?,?)",
                (wid, key, fingerprint, canonical(plan), timestamp, timestamp),
            )
            for step in plan["workflow"]["steps"]:
                self.db.execute(
                    "INSERT INTO steps(workflow_id,id,status,updated) VALUES(?,?,?,?)",
                    (wid, step["id"], "WAITING", timestamp),
                )
            self._event(wid, "workflow.submitted")
        return {"workflow_id": wid, "created": True, "plan_sha256": fingerprint}

    def approve(self, wid, plan_sha256, kinds, operator):
        identifier(operator)
        row, plan = self.record(wid), self.plan(wid)
        required = {binding["kind"] for binding in plan["adapters"].values()}
        if row["cancelled"] or row["hash"] != plan_sha256 or not required <= set(kinds):
            raise ValueError("APPROVAL_SCOPE_OR_DIGEST_MISMATCH")
        approval = canonical(
            {"plan_sha256": plan_sha256, "kinds": sorted(set(kinds)), "operator": operator}
        )
        with self.db:
            if row["approval"] and row["approval"] != approval:
                raise ValueError("APPROVAL_IMMUTABLE")
            if not row["approval"]:
                self.db.execute("UPDATE workflows SET approval=? WHERE id=?", (approval, wid))
                self._event(wid, "workflow.approved")
        return self.view(wid)

    def steps(self, wid):
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT * FROM steps WHERE workflow_id=? ORDER BY rowid", (wid,)
            )
        ]

    def set_step(self, wid, sid, status, owner_id=None, evidence="NOT_VERIFIED", error=None):
        if status not in STEP_STATES:
            raise ValueError("INVALID_STEP_STATE")
        with self.db:
            current = self.db.execute(
                "SELECT status,owner_id FROM steps WHERE workflow_id=? AND id=?", (wid, sid)
            ).fetchone()
            if current is None:
                raise ValueError("STEP_NOT_FOUND")
            if current["status"] in TERMINAL:
                return
            if current["owner_id"] and owner_id and current["owner_id"] != owner_id:
                raise ValueError("OWNER_IDENTITY_MISMATCH")
            self.db.execute(
                "UPDATE steps SET status=?,owner_id=COALESCE(?,owner_id),evidence=?,error=?,updated=? WHERE workflow_id=? AND id=?",
                (status, owner_id, evidence, error, now(), wid, sid),
            )
            self._event(wid, "step." + status.lower(), sid)

    def cancel(self, wid):
        self.record(wid)
        with self.db:
            self.db.execute("UPDATE workflows SET cancelled=1 WHERE id=?", (wid,))
            self._event(wid, "workflow.cancel_requested")
        return self.view(wid)

    def hint(self, event):
        exact(event, {"schema", "event_id", "workflow_id", "source", "type"})
        if event["schema"] != "quant.workflow_event.v1" or event["type"] != "owner.changed":
            raise ValueError("INVALID_EVENT")
        identifier(event["event_id"])
        identifier(event["source"])
        self.record(event["workflow_id"])
        fingerprint = digest(event)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            old = self.db.execute(
                "SELECT hash FROM events WHERE event_id=?", (event["event_id"],)
            ).fetchone()
            if old:
                if old["hash"] != fingerprint:
                    raise ValueError("EVENT_IDEMPOTENCY_CONFLICT")
                return {"created": False, "event_id": event["event_id"]}
            self.db.execute(
                "INSERT INTO events(workflow_id,event_id,hash,type,created) VALUES(?,?,?,?,?)",
                (event["workflow_id"], event["event_id"], fingerprint, event["type"], now()),
            )
        return {"created": True, "event_id": event["event_id"]}

    def events(self, wid, after=0):
        self.record(wid)
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT seq,type,step_id,created FROM events WHERE workflow_id=? AND seq>? ORDER BY seq LIMIT 500",
                (wid, after),
            )
        ]

    def scheduler_ids(self):
        return [
            row[0]
            for row in self.db.execute(
                "SELECT DISTINCT workflow_id FROM steps WHERE status NOT IN ('SUCCEEDED','FAILED','CANCELLED')"
            )
        ]

    def list(self):
        return [
            self.view(row[0])
            for row in self.db.execute("SELECT id FROM workflows ORDER BY created DESC LIMIT 100")
        ]

    def view(self, wid):
        row, plan = self.record(wid), self.plan(wid)
        steps = self.steps(wid)
        states = {step["status"] for step in steps}
        if states <= {"SUCCEEDED"}:
            status = "SUCCEEDED"
        elif states <= TERMINAL and row["cancelled"]:
            status = "CANCELLED"
        elif "FAILED" in states:
            status = "FAILED"
        elif "UNKNOWN" in states or "DISPATCHING" in states:
            status = "NEEDS_RECONCILIATION"
        elif "BLOCKED" in states:
            status = "BLOCKED"
        elif row["cancelled"]:
            status = "CANCELLING"
        elif not row["approval"]:
            status = "AWAITING_APPROVAL"
        else:
            status = "ACTIVE"
        definitions = {step["id"]: step for step in plan["workflow"]["steps"]}
        projected = []
        for step in steps:
            definition = definitions[step["id"]]
            binding = plan["adapters"][definition["adapter"]]
            projected.append(
                {
                    "id": step["id"],
                    "kind": binding["kind"],
                    "status": step["status"],
                    "owner_id": step["owner_id"],
                    "depends_on": definition["depends_on"],
                    "evidence_status": step["evidence"],
                    "error_code": step["error"],
                    "updated_at": step["updated"],
                    "budgets": {
                        key: value
                        for key, value in binding.get("budgets", {}).items()
                        if key in {"wall_seconds", "memory_mb"}
                        and type(value) in {int, float}
                        and value > 0
                        and value < float("inf")
                    },
                }
            )
        return {
            "schema": "quant.workflow_view.v1",
            "workflow_id": wid,
            "title": plan["workflow"]["title"],
            "status": status,
            "plan_sha256": row["hash"],
            "approved": row["approval"] is not None,
            "cancel_requested": bool(row["cancelled"]),
            "created_at": row["created"],
            "updated_at": row["updated"],
            "steps": projected,
            "skills": [
                {
                    key: skill[key]
                    for key in (
                        "id",
                        "owner_repo",
                        "revision",
                        "sha256",
                        "permissions",
                        "input_contract",
                        "output_contract",
                    )
                }
                for skill in plan["skills"]
            ],
            "research_validated": False,
            "promotion_authorized": False,
            "freshness": "last_observed_owner_state",
        }
