"""Offline public demo built from the same pinned owner and scheduler contracts."""

import json
import shlex
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import sample_owner
from .contracts import build_plan, digest, file_sha
from .scheduler import Scheduler
from .store import Store


def run_demo(output_root):
    root = Path(output_root).expanduser().resolve() / ("demo-" + str(uuid.uuid4()))
    root.mkdir(parents=True, exist_ok=False)
    database = root / "orchestrator.db"
    store = Store(database)
    views = []
    try:
        for index, score in enumerate((0.12, 0.08), 1):
            name = f"synthetic-comparison-{index}"
            request_path = root / (name + ".request.json")
            request_path.write_text(
                json.dumps(
                    {
                        "idempotency_key": name,
                        "synthetic_metrics": {"illustrative_score": score},
                        "budgets": {},
                    }
                )
            )
            adapter = {
                "kind": "runtime",
                "command": [
                    sys.executable,
                    "-I",
                    str(Path(sample_owner.__file__).resolve()),
                    str(root / "synthetic-owner"),
                ],
                "request": str(request_path),
                "queue": False,
            }
            workflow = {
                "schema": "quant.workflow.v1",
                "idempotency_key": name,
                "title": f"Synthetic comparison {index}: illustration only",
                "steps": [
                    {"id": "compute", "adapter": "sample", "depends_on": [], "skills": []},
                    {
                        "id": "qualification",
                        "adapter": "sample",
                        "depends_on": ["compute"],
                        "skills": [],
                        "requires_evidence": {"compute": ["historical_pit"]},
                    },
                ],
            }
            plan = build_plan(
                workflow,
                {
                    "schema": "quant.orchestrator_config.v1",
                    "adapters": {"sample": adapter},
                    "catalog": [],
                },
            )
            (root / (name + ".plan.json")).write_text(json.dumps(plan, indent=2))
            wid = store.submit(plan)["workflow_id"]
            store.approve(wid, plan["plan_sha256"], ["runtime"], "synthetic-demo")
            Scheduler(store).tick(wid)
            # Explicit synthetic attestations illustrate TTL; they never prove market PIT.
            clock = datetime.now(UTC)
            scope = {
                "data_sha256": file_sha(request_path),
                "strategy_sha256": digest({"synthetic_strategy": index}),
                "universe_sha256": digest(["SYNTHETIC_A", "SYNTHETIC_B"]),
                "as_of": "2020-12-31T16:00:00Z",
                "sample_start": "2020-01-01",
                "sample_end": "2020-12-31",
            }
            store.observe(
                wid,
                "compute",
                {
                    "input_integrity": {
                        "status": "verified",
                        "source": "quant-backtest-runtime",
                        "evidence_sha256": digest({"synthetic": True, "scope": scope}),
                        "scope": scope,
                        "assessed_at": (clock - timedelta(days=2)).isoformat(),
                        "valid_until": (
                            clock + timedelta(days=1) if index == 1 else clock - timedelta(days=1)
                        ).isoformat(),
                    }
                },
            )
            views.append(store.view(wid))
        from .analysis_reports import record_evaluation
        from .evaluation import reference_trace

        record_evaluation(store, reference_trace())
        from .history import install_history

        records = []
        for number, classification in enumerate(("operational_failure", "research_conclusion")):
            records.append(
                {
                    "record_id": digest({"synthetic_record": number}),
                    "source_kind": "campaign",
                    "status": "BLOCKED" if number == 0 else "DISCARDED",
                    "stage": "SYNTHETIC",
                    "decision": None if number == 0 else "DISCARDED",
                    "classification": classification,
                    "evidence_stage": "not_verified",
                    "evidence_handles": [],
                    "topic_tags": ["synthetic-demo"],
                    "reason_codes": ["DEMO_ONLY"],
                    "revisit_conditions": [],
                    "provenance": {
                        "source_revision": "0" * 40,
                        "source_database_sha256": digest({"synthetic": True}),
                        "annotations_sha256": None,
                        "owner_source_revision": None,
                        "dataset_fingerprint_sha256": None,
                    },
                }
            )
        example = {
            "schema": "quant.research_history.v1",
            "owner": "quant-research",
            "source_revision": "0" * 40,
            "source_id": "synthetic-public-demo",
            "records": records,
        }
        history_path = root / "synthetic-history.json"
        history_path.write_text(json.dumps(example, indent=2))
        install_history(store, history_path, file_sha(history_path))
    finally:
        store.close()
    result = {
        "schema": "quant.public_demo.v1",
        "synthetic": True,
        "run_directory": str(root),
        "database_path": str(database),
        "workflow_ids": [v["workflow_id"] for v in views],
        "workflows": views,
        "ui_command": "quant-task --database " + shlex.quote(str(database)) + " serve-api",
        "limitations": [
            "Synthetic protocol peer, not a market engine or model evaluation.",
            "Historical PIT evidence is unknown; qualification remains blocked.",
        ],
    }
    (root / "demo.json").write_text(json.dumps(result, indent=2))
    return result
