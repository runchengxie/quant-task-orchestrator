"""Explicit, hash-approved read-only data readiness shadow; no schedule cutover."""

import hashlib
import json
import os
import sqlite3
import stat
import subprocess
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .contracts import build_plan, exact, file_sha, verify_bindings
from .event_inbox import safe_path
from .owners import OwnerError
from .scheduler import Scheduler
from .store import Store


def run_shadow(config_file, expected_sha256, output_root):
    started = time.monotonic()
    config_file = Path(config_file).absolute()
    safe_path(config_file)
    descriptor = os.open(config_file, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1_048_576:
            raise ValueError("INVALID_SHADOW_CONFIG_FILE")
        body = source.read(1_048_577)
    if len(body) > 1_048_576 or hashlib.sha256(body).hexdigest() != expected_sha256:
        raise ValueError("SHADOW_CONFIG_CHANGED")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    config = json.loads(
        body.decode("utf-8"),
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")),
    )
    exact(config, {"schema", "adapters", "catalog"})
    adapters = config["adapters"]
    if (
        config["schema"] != "quant.orchestrator_config.v1"
        or config["catalog"] != []
        or not isinstance(adapters, dict)
        or not 1 <= len(adapters) <= 20
        or any(
            not isinstance(value, dict) or value.get("kind") not in {"data", "raw_observation"}
            for value in adapters.values()
        )
    ):
        raise ValueError("SHADOW_REQUIRES_READ_ONLY_DATA")
    run_id = uuid.uuid4().hex
    workflow = {
        "schema": "quant.workflow.v1",
        "idempotency_key": "data-shadow-" + run_id,
        "title": "Read-only data readiness shadow",
        "steps": [
            {"id": name, "adapter": name, "depends_on": [], "skills": []}
            for name in sorted(adapters)
        ],
    }
    root = safe_path(output_root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    output = root / run_id
    output.mkdir(mode=0o700)
    plan, wid, view, failure_phase = None, None, {"status": "FAILED", "steps": []}, "binding"
    try:
        plan = build_plan(workflow, config)
        if file_sha(config_file) != expected_sha256:
            raise ValueError("SHADOW_CONFIG_CHANGED")
        failure_phase = "execution"
        with Store(output / "workflow.sqlite") as store:
            wid = store.submit(plan)["workflow_id"]
            store.approve(
                wid,
                plan["plan_sha256"],
                sorted({x["kind"] for x in adapters.values()}),
                "readonly-data-shadow",
            )
            view = Scheduler(store).tick(wid)
        verify_bindings(plan)
        failure_phase = None
    except (
        OwnerError,
        ValueError,
        OSError,
        TypeError,
        KeyError,
        sqlite3.Error,
        subprocess.SubprocessError,
    ):
        # Preserve a failed observation without exporting private exception text.
        view = {"status": "FAILED", "steps": []}
    result = {
        "schema": "quant.data_shadow.v1",
        "observed_at": datetime.now(UTC).isoformat(),
        "duration_seconds": time.monotonic() - started,
        "run_id": run_id,
        "workflow_id": wid,
        "config_sha256": expected_sha256,
        "plan_sha256": plan["plan_sha256"] if plan else None,
        "failure_phase": failure_phase,
        "shadow_only": True,
        "status": view["status"],
        "steps": view["steps"],
        "production_schedule_changed": False,
        "qualified_research_ready": False,
        "promotion_authorized": False,
        "new_model_calls": 0,
    }
    records = [("assessment.json", result)]
    if plan is not None:
        records.insert(0, ("plan.json", plan))
    for name, value in records:
        path = output / name
        with path.open("x") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
        path.chmod(0o600)
    return {**result, "assessment_file": str(output / "assessment.json")}
