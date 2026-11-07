"""Opt-in actual installed Runtime; all inputs/output stay task-local and synthetic."""

import json
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from quant_task_orchestrator.contracts import build_plan
from quant_task_orchestrator.scheduler import Scheduler
from quant_task_orchestrator.store import Store


@unittest.skipUnless(
    os.environ.get("QUANT_RUNTIME_CLI")
    and os.environ.get("QUANT_RUNTIME_PYTHON")
    and os.environ.get("QUANT_RUNTIME_EXAMPLE"),
    "explicit installed Runtime fixture required",
)
class RealRuntimeTests(unittest.TestCase):
    def test_actual_runtime_submission_recovery_result_and_single_job(self):
        with tempfile.TemporaryDirectory(prefix="orchestrator-runtime-") as directory:
            root = Path(directory)
            subprocess.run(
                [
                    os.environ["QUANT_RUNTIME_PYTHON"],
                    os.environ["QUANT_RUNTIME_EXAMPLE"],
                    "--output",
                    str(root),
                ],
                check=True,
                capture_output=True,
            )
            command = [
                os.environ["QUANT_RUNTIME_CLI"],
                "--database",
                str(root / "jobs.sqlite"),
                "--artifact-root",
                str(root / "artifacts"),
                "--result-root",
                str(root / "results"),
                "--error-format",
                "json",
            ]
            if os.environ.get("QUANT_RUNTIME_ADAPTER_PYTHON"):
                command.extend(["--python-executable", os.environ["QUANT_RUNTIME_ADAPTER_PYTHON"]])
            # The read-only lookup contract requires an existing owner database. The
            # operator creates its isolated instance, not the coordinator.
            initialize = subprocess.run([*command, "recover"], capture_output=True, text=True)
            self.assertEqual(initialize.returncode, 0, initialize.stderr)
            config = {
                "schema": "quant.orchestrator_config.v1",
                "adapters": {
                    "backtest": {
                        "kind": "runtime",
                        "command": command,
                        "request": str(root / "request.json"),
                        "queue": False,
                    }
                },
                "catalog": [],
            }
            workflow = {
                "schema": "quant.workflow.v1",
                "idempotency_key": "synthetic-study",
                "title": "Synthetic acceptance",
                "steps": [
                    {"id": "backtest", "adapter": "backtest", "depends_on": [], "skills": []}
                ],
            }
            workflow["steps"].append(
                {
                    "id": "verify-original-job",
                    "adapter": "backtest",
                    "depends_on": ["backtest"],
                    "skills": [],
                }
            )
            plan = build_plan(workflow, config)
            with Store(root / "workflow.sqlite") as store:
                wid = store.submit(plan)["workflow_id"]
                store.approve(wid, plan["plan_sha256"], ["runtime"], "acceptance")
                Scheduler(store).tick(wid)
            with Store(root / "workflow.sqlite") as store:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    view = Scheduler(store).tick(wid)
                    if view["status"] == "SUCCEEDED":
                        break
                    time.sleep(0.2)
                self.assertEqual(view["status"], "SUCCEEDED", json.dumps(view))
                self.assertEqual(view["steps"][0]["evidence_status"], "RESULT_INTEGRITY_VERIFIED")
                self.assertFalse(view["promotion_authorized"])
                # Same key recovers the same workflow, including after process restart.
                self.assertEqual(store.submit(plan)["workflow_id"], wid)
            import sqlite3

            with sqlite3.connect(root / "jobs.sqlite") as database:
                self.assertEqual(
                    database.execute("SELECT COUNT(*) FROM backtest_jobs").fetchone()[0], 1
                )
