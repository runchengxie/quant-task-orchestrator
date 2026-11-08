"""Durable workflow state and explicit, allowlisted public projections."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .contracts import canonical, digest, exact, identifier
from .evidence import project_evidence
from .metrics import step_metrics
from .recovery import recovery_for

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
                CREATE TABLE IF NOT EXISTS economic_result_snapshots(
                    snapshot_sha256 TEXT PRIMARY KEY, payload BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS research_history_snapshots(
                    snapshot_sha256 TEXT PRIMARY KEY, source_revision TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS evaluation_reports(
                    report_sha256 TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workflows(
                    id TEXT PRIMARY KEY, key TEXT UNIQUE NOT NULL, hash TEXT NOT NULL,
                    plan TEXT NOT NULL, approval TEXT, cancelled INTEGER NOT NULL DEFAULT 0,
                    created TEXT NOT NULL, updated TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS steps(
                    workflow_id TEXT NOT NULL, id TEXT NOT NULL, status TEXT NOT NULL,
                    owner_id TEXT, evidence TEXT NOT NULL DEFAULT 'NOT_VERIFIED', error TEXT,
                    updated TEXT NOT NULL, PRIMARY KEY(workflow_id,id));
                CREATE TABLE IF NOT EXISTS observations(
                    workflow_id TEXT NOT NULL, step_id TEXT NOT NULL,
                    snapshot TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    PRIMARY KEY(workflow_id,step_id));
                CREATE TABLE IF NOT EXISTS execution_snapshots(
                    workflow_id TEXT NOT NULL, step_id TEXT NOT NULL,
                    snapshot TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    PRIMARY KEY(workflow_id,step_id));
                CREATE TABLE IF NOT EXISTS step_telemetry(
                    workflow_id TEXT NOT NULL, step_id TEXT NOT NULL,
                    owner_calls INTEGER NOT NULL DEFAULT 0, owner_errors INTEGER NOT NULL DEFAULT 0,
                    owner_call_wall_seconds REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY(workflow_id,step_id));
                CREATE TABLE IF NOT EXISTS transitions(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, workflow_id TEXT NOT NULL,
                    step_id TEXT NOT NULL, status TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS workflow_signals(
                    event_id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL,
                    source TEXT NOT NULL, type TEXT NOT NULL);
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
                self.db.execute(
                    "INSERT INTO transitions(workflow_id,step_id,status,created) VALUES(?,?,?,?)",
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
        with self.db:
            self._set_step(wid, sid, status, owner_id, evidence, error)

    def _set_step(self, wid, sid, status, owner_id=None, evidence="NOT_VERIFIED", error=None):
        if status not in STEP_STATES:
            raise ValueError("INVALID_STEP_STATE")
        current = self.db.execute(
            "SELECT status,owner_id,evidence,error FROM steps WHERE workflow_id=? AND id=?",
            (wid, sid),
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
        if (current["status"], current["owner_id"], current["evidence"], current["error"]) != (
            status,
            owner_id or current["owner_id"],
            evidence,
            error,
        ):
            if current["status"] != status:
                self.db.execute(
                    "INSERT INTO transitions(workflow_id,step_id,status,created) VALUES(?,?,?,?)",
                    (wid, sid, status, now()),
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
        if event["schema"] != "quant.workflow_event.v1" or event["type"] not in {
            "owner.changed",
            "data.published",
            "report.published",
        }:
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
            self.db.execute(
                "INSERT INTO workflow_signals VALUES(?,?,?,?)",
                (event["event_id"], event["workflow_id"], event["source"], event["type"]),
            )
        return {"created": True, "event_id": event["event_id"]}

    def events(self, wid, after=0, *, tail=None):
        self.record(wid)
        if tail is not None:
            if type(tail) is not int or not 1 <= tail <= 500:
                raise ValueError("INVALID_EVENT_LIMIT")
            return list(
                reversed(
                    [
                        dict(row)
                        for row in self.db.execute(
                            "SELECT seq,type,step_id,created FROM events WHERE workflow_id=? ORDER BY seq DESC LIMIT ?",
                            (wid, tail),
                        )
                    ]
                )
            )
        return [
            dict(row)
            for row in self.db.execute(
                "SELECT seq,type,step_id,created FROM events WHERE workflow_id=? AND seq>? ORDER BY seq LIMIT 500",
                (wid, after),
            )
        ]

    def trigger_ready(self, wid, plan=None):
        trigger = (plan or self.plan(wid))["workflow"].get("trigger")
        if not trigger:
            return True
        exists = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='workflow_signals'"
        ).fetchone()
        return bool(
            exists
            and self.db.execute(
                "SELECT 1 FROM workflow_signals WHERE workflow_id=? AND source=? AND type=? LIMIT 1",
                (wid, trigger["source"], trigger["event_type"]),
            ).fetchone()
        )

    def scheduler_ids(self):
        return [
            row[0]
            for row in self.db.execute(
                "SELECT DISTINCT workflow_id FROM steps WHERE status NOT IN ('SUCCEEDED','FAILED','CANCELLED')"
            )
        ]

    def list(self, limit=100, offset=0):
        if (
            type(limit) is not int
            or type(offset) is not int
            or not 1 <= limit <= 1000
            or offset < 0
        ):
            raise ValueError("INVALID_PAGINATION")
        return [
            self.view(row[0])
            for row in self.db.execute(
                "SELECT id FROM workflows ORDER BY created DESC,id LIMIT ? OFFSET ?",
                (limit, offset),
            )
        ]

    def pagination(self, limit=100, offset=0):
        total = self.db.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
        return {
            "limit": limit,
            "offset": offset,
            "total": total,
            "has_more": offset + limit < total,
        }

    def auxiliary(self, table, wid, sid):
        # These query strings are static internal table names, never user input.
        if table not in {"observations", "step_telemetry", "transitions", "execution_snapshots"}:
            raise ValueError("INVALID_AUXILIARY_TABLE")
        exists = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if not exists:
            return []
        return [
            dict(row)
            for row in self.db.execute(
                f"SELECT * FROM {table} WHERE workflow_id=? AND step_id=?"
                + (" ORDER BY seq" if table == "transitions" else ""),
                (wid, sid),
            )
        ]

    def observe(self, wid, sid, checks):
        step = next((row for row in self.steps(wid) if row["id"] == sid), None)
        if step is None:
            raise ValueError("STEP_NOT_FOUND")
        definition = next(row for row in self.plan(wid)["workflow"]["steps"] if row["id"] == sid)
        kind = self.plan(wid)["adapters"][definition["adapter"]]["kind"]
        safe = project_evidence(kind, step["evidence"], checks)["checks"]
        with self.db:
            self.db.execute(
                "INSERT INTO observations VALUES(?,?,?,?) ON CONFLICT(workflow_id,step_id) DO UPDATE SET snapshot=excluded.snapshot,recorded_at=excluded.recorded_at",
                (wid, sid, canonical(safe), now()),
            )

    def complete_step(self, wid, sid, status, owner_id, evidence, checks, execution=None):
        definition = next(row for row in self.plan(wid)["workflow"]["steps"] if row["id"] == sid)
        kind = self.plan(wid)["adapters"][definition["adapter"]]["kind"]
        safe = project_evidence(kind, evidence, checks)["checks"]
        from .codex_owner import project_execution

        safe_execution = project_execution(execution)
        # Final status, evidence and execution snapshots commit together.
        with self.db:
            self._set_step(wid, sid, status, owner_id, evidence)
            self.db.execute(
                "INSERT INTO observations VALUES(?,?,?,?) ON CONFLICT(workflow_id,step_id) DO UPDATE SET snapshot=excluded.snapshot,recorded_at=excluded.recorded_at",
                (wid, sid, canonical(safe), now()),
            )
            if safe_execution is not None:
                self.db.execute(
                    "INSERT INTO execution_snapshots VALUES(?,?,?,?) "
                    "ON CONFLICT(workflow_id,step_id) DO UPDATE SET "
                    "snapshot=excluded.snapshot,recorded_at=excluded.recorded_at",
                    (wid, sid, canonical(safe_execution), now()),
                )

    def was_dispatched(self, wid, sid):
        row = self.db.execute(
            "SELECT owner_id FROM steps WHERE workflow_id=? AND id=?", (wid, sid)
        ).fetchone()
        return (
            bool(row and row[0])
            or self.db.execute(
                "SELECT 1 FROM events WHERE workflow_id=? AND step_id=? AND type='step.dispatching' LIMIT 1",
                (wid, sid),
            ).fetchone()
            is not None
        )

    def bind_owner_id(self, wid, sid, owner_id):
        identifier(owner_id)
        with self.db:
            current = self.db.execute(
                "SELECT owner_id FROM steps WHERE workflow_id=? AND id=?", (wid, sid)
            ).fetchone()
            if current is None or (current[0] and current[0] != owner_id):
                raise ValueError("OWNER_IDENTITY_MISMATCH")
            self.db.execute(
                "UPDATE steps SET owner_id=? WHERE workflow_id=? AND id=?", (owner_id, wid, sid)
            )

    def record_call(self, wid, sid, success, seconds):
        if (
            type(success) is not bool
            or type(seconds) not in {int, float}
            or not 0 <= seconds < float("inf")
        ):
            raise ValueError("INVALID_CALL_MEASUREMENT")
        with self.db:
            self.db.execute(
                "INSERT INTO step_telemetry VALUES(?,?,1,?,?) ON CONFLICT(workflow_id,step_id) DO UPDATE SET owner_calls=owner_calls+1,owner_errors=owner_errors+excluded.owner_errors,owner_call_wall_seconds=owner_call_wall_seconds+excluded.owner_call_wall_seconds",
                (wid, sid, int(not success), seconds),
            )

    def execution(self, wid, sid):
        from .codex_owner import project_execution

        rows = self.auxiliary("execution_snapshots", wid, sid)
        return project_execution(json.loads(rows[0]["snapshot"])) if rows else None

    def execution_totals(self):
        exists = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='execution_snapshots'"
        ).fetchone()
        if not exists:
            return {"observed_tokens": 0, "usage_unknown_count": 0}
        from .codex_owner import project_execution

        unique = {}
        for row in self.db.execute("SELECT snapshot FROM execution_snapshots"):
            execution = project_execution(json.loads(row[0]))
            key = (execution["owner_plan_sha256"], execution["owner_id"], execution["turn"])
            old = unique.get(key)
            number = execution["observed_tokens"]
            if old is None or number is not None:
                unique[key] = number
        return {
            "observed_tokens": sum(n for n in unique.values() if n is not None),
            "usage_unknown_count": sum(n is None for n in unique.values()),
        }

    def metrics(self):
        states = {
            row[0]: row[1]
            for row in self.db.execute("SELECT status,COUNT(*) FROM steps GROUP BY status")
        }
        exists = self.db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='step_telemetry'"
        ).fetchone()
        calls = (
            self.db.execute(
                "SELECT COALESCE(SUM(owner_calls),0),COALESCE(SUM(owner_errors),0) FROM step_telemetry"
            ).fetchone()
            if exists
            else (0, 0)
        )
        return {
            "schema": "quant.orchestrator_metrics.v1",
            **self.execution_totals(),
            "workflow_count": self.db.execute("SELECT COUNT(*) FROM workflows").fetchone()[0],
            "step_count": sum(states.values()),
            "states": states,
            "owner_calls": calls[0],
            "owner_errors": calls[1],
            "operator_interventions": self.db.execute(
                "SELECT COUNT(*) FROM events WHERE type IN ('workflow.approved','workflow.cancel_requested')"
            ).fetchone()[0],
            "model_cost_usd": None,
            "cpu_seconds": None,
        }

    @staticmethod
    def evidence_context(definition):
        from .evidence_scope import validate_context

        try:
            return validate_context(definition["evidence_context"])
        except (KeyError, ValueError, TypeError, OverflowError):
            return None

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
        elif not self.trigger_ready(wid, plan):
            status = "AWAITING_EVENT"
        else:
            status = "ACTIVE"
        definitions = {step["id"]: step for step in plan["workflow"]["steps"]}
        projected = []
        for step in steps:
            definition = definitions[step["id"]]
            binding = plan["adapters"][definition["adapter"]]
            observations = self.auxiliary("observations", wid, step["id"])
            telemetry = self.auxiliary("step_telemetry", wid, step["id"])
            evidence = project_evidence(
                binding["kind"],
                step["evidence"],
                json.loads(observations[0]["snapshot"]) if observations else {},
            )
            projected.append(
                {
                    "id": step["id"],
                    "kind": binding["kind"],
                    "status": step["status"],
                    "owner_id": step["owner_id"],
                    "depends_on": definition["depends_on"],
                    "requires_evidence": definition.get("requires_evidence", {}),
                    "evidence_context": self.evidence_context(definition),
                    "evidence_status": step["evidence"],
                    "error_code": step["error"],
                    "updated_at": step["updated"],
                    "evidence": evidence,
                    "execution": self.execution(wid, step["id"]),
                    "recovery": recovery_for(
                        step["status"],
                        step["error"],
                        binding["kind"],
                        step["evidence"],
                        row["approval"] is not None,
                    ),
                    "metrics": step_metrics(
                        self.auxiliary("transitions", wid, step["id"]),
                        telemetry[0] if telemetry else None,
                    ),
                    "owner_revision": binding.get("owner_revision"),
                    "observed_at": observations[0]["recorded_at"] if observations else None,
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
            "trigger": plan["workflow"].get("trigger"),
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
