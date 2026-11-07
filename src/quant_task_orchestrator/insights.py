"""Read-only engineering comparisons and hypothetical dependency impact."""

from __future__ import annotations

import math
import re
from datetime import date, datetime

from .contracts import identifier

LIMITS = [
    "Engineering differences do not establish economic causality.",
    "Owner economic metrics are not exported; economic comparison is unavailable.",
    "Missing usage is unknown, never zero; model cost is unavailable.",
    "Step identity is matched by step id only; renamed steps appear removed and added.",
]
CONTEXT = (
    "data_sha256",
    "strategy_sha256",
    "universe_sha256",
    "as_of",
    "sample_start",
    "sample_end",
)


def _number(value):
    return value if type(value) in {int, float} and math.isfinite(value) and value >= 0 else None


def _hash(value, length=64):
    return (
        value
        if isinstance(value, str) and re.fullmatch("[0-9a-f]{" + str(length) + "}", value)
        else None
    )


def _safe_context(value):
    """Reject the entire context unless every value satisfies its public contract."""
    if not isinstance(value, dict) or set(value) != set(CONTEXT):
        return {}
    if any(_hash(value[key]) is None for key in CONTEXT[:3]):
        return {}
    stamp = value["as_of"]
    if not isinstance(stamp, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", stamp
    ):
        return {}
    try:
        datetime.fromisoformat(stamp)
        for key in ("sample_start", "sample_end"):
            if (
                not isinstance(value[key], str)
                or date.fromisoformat(value[key]).isoformat() != value[key]
            ):
                return {}
        if value["sample_start"] > value["sample_end"]:
            return {}
    except ValueError:
        return {}
    return {key: value[key] for key in CONTEXT}


def _projection(store, wid):
    plan, view = store.plan(wid), store.view(wid)
    views = {s["id"]: s for s in view["steps"]}
    skills = {s["id"]: s for s in plan["skills"]}
    result = {}
    for definition in plan["workflow"]["steps"]:
        binding = plan["adapters"][definition["adapter"]]
        public = views[definition["id"]]
        execution = public.get("execution") or {}
        context = definition.get("evidence_context", {})
        result[definition["id"]] = {
            "kind": binding["kind"],
            "owner_revision": _hash(binding.get("owner_revision"), 40),
            "owner_plan_sha256": _hash(binding.get("owner_plan_sha256")),
            "owner_request_sha256": _hash(binding.get("owner_request_sha256")),
            "pinned_input_sha256": sorted(
                {_hash(v) for v in binding.get("pins", {}).values() if _hash(v) is not None}
            ),
            "skills": [
                {
                    "id": sid,
                    "revision": _hash(skills[sid].get("revision"), 40),
                    "sha256": _hash(skills[sid].get("sha256")),
                }
                for sid in sorted(definition["skills"])
            ],
            "depends_on": sorted(definition["depends_on"]),
            "budgets": {
                k: _number(v)
                for k, v in binding.get("budgets", {}).items()
                if k in {"wall_seconds", "memory_mb", "max_tokens"}
            },
            "evidence_context": _safe_context(context),
            "evidence": public["evidence"],
            "observed_usage": {
                "observed_tokens": _number(execution.get("observed_tokens")),
                "usage": {
                    k: _number((execution.get("usage") or {}).get(k))
                    for k in (
                        "input_tokens",
                        "cached_input_tokens",
                        "output_tokens",
                        "reasoning_output_tokens",
                    )
                },
                "model_cost_usd": None,
            },
        }
    return result


def compare_workflows(store, before_id: str, after_id: str) -> dict:
    """Compare allowlisted projections without claiming investment performance."""
    before, after = _projection(store, before_id), _projection(store, after_id)
    rows = []
    for sid in sorted(before.keys() | after.keys()):
        left, right = before.get(sid), after.get(sid)
        changed = sorted(k for k in left if left[k] != right[k]) if left and right else []
        status = (
            "added"
            if left is None
            else "removed"
            if right is None
            else "changed"
            if changed
            else "unchanged"
        )
        rows.append(
            {"id": sid, "status": status, "changed_fields": changed, "before": left, "after": right}
        )
    return {
        "schema": "quant.workflow_comparison.v1",
        "before_workflow_id": before_id,
        "after_workflow_id": after_id,
        "steps": rows,
        "economic_comparison": {
            "status": "unavailable",
            "reason": "OWNER_ECONOMIC_METRICS_NOT_EXPORTED",
        },
        "comparison_limits": list(LIMITS),
    }


def _proposal(value):
    required = {"schema", "kind", "previous", "next"}
    if not isinstance(value, dict) or set(value) not in (required, required | {"target"}):
        raise ValueError("INVALID_CHANGE_PROPOSAL")
    if value["schema"] != "quant.change_proposal.v1" or value["kind"] not in (
        "owner_revision",
        "skill_revision",
        "pinned_input",
    ):
        raise ValueError("INVALID_CHANGE_PROPOSAL")
    length = 64 if value["kind"] == "pinned_input" else 40
    if (
        not _hash(value["previous"], length)
        or not _hash(value["next"], length)
        or value["previous"] == value["next"]
    ):
        raise ValueError("INVALID_CHANGE_PROPOSAL")
    if "target" in value:
        identifier(value["target"])


def _graph(steps):
    definitions = {s["id"]: s for s in steps}
    done = set()
    while len(done) < len(definitions):
        ready = {
            sid
            for sid, step in definitions.items()
            if sid not in done and set(step["depends_on"]) <= done
        }
        if not ready:
            raise ValueError("CYCLIC_OR_MISSING_DEPENDENCY")
        done.update(ready)
    return definitions


def _impact_snapshot(store, proposal: dict) -> dict:
    """Scan every stored workflow; report direct references and DAG successors only."""
    _proposal(proposal)
    target, kind, previous = proposal.get("target"), proposal["kind"], proposal["previous"]
    affected, scanned, offset = [], 0, 0
    while True:
        page = store.list(limit=100, offset=offset)
        if not page:
            break
        for public in page:
            wid = public["workflow_id"]
            plan = store.plan(wid)
            definitions = _graph(plan["workflow"]["steps"])
            skills = {s["id"]: s for s in plan["skills"]}
            direct = set()
            for sid, step in definitions.items():
                adapter = plan["adapters"][step["adapter"]]
                if kind == "skill_revision":
                    match = any(
                        (target is None or target == skill_id)
                        and skills[skill_id]["revision"] == previous
                        for skill_id in step["skills"]
                    )
                else:
                    match = (target is None or target == step["adapter"]) and (
                        adapter.get("owner_revision") == previous
                        if kind == "owner_revision"
                        else previous in adapter.get("pins", {}).values()
                    )
                if match:
                    direct.add(sid)
            all_affected = set(direct)
            while True:
                successors = {
                    sid
                    for sid, step in definitions.items()
                    if set(step["depends_on"]) & all_affected
                }
                if successors <= all_affected:
                    break
                all_affected.update(successors)
            if direct:
                affected.append(
                    {
                        "workflow_id": wid,
                        "direct_steps": sorted(direct),
                        "downstream_steps": sorted(all_affected - direct),
                        "required_new_plan": True,
                        "approval_review": True,
                    }
                )
            scanned += 1
        offset += len(page)
    return {
        "schema": "quant.change_impact.v1",
        "execution_authorized": False,
        "proposal": dict(proposal),
        "affected_workflows": affected,
        "scan": {
            "scope": "all_stored_workflows",
            "workflows_scanned": scanned,
            "truncated": False,
            "consistency": "sqlite_read_snapshot",
        },
        "limits": [
            "Preview only; no plans, approvals, executions or reruns are changed.",
            "Inventory reflects the SQLite read snapshot, excluding later concurrent commits.",
            "Pinned input matching uses exact content hashes; paths are not exposed.",
        ],
    }


def impact_preview(store, proposal: dict) -> dict:
    """Read one consistent SQLite snapshot without committing a caller transaction."""
    _proposal(proposal)
    # A nested savepoint keeps an existing caller transaction and its changes intact.
    # The first read establishes the snapshot for every subsequent page and projection.
    store.db.execute("SAVEPOINT insight_preview")
    try:
        return _impact_snapshot(store, proposal)
    finally:
        store.db.execute("RELEASE SAVEPOINT insight_preview")
