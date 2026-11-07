"""Content sealing is stronger than metadata but never proves historical PIT."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.contracts import build_plan
from quant_task_orchestrator.scheduler import Scheduler
from quant_task_orchestrator.store import Store


class RawObservationTests(unittest.TestCase):
    def test_verified_bytes_unblock_integrity_but_not_pit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "manifest.yml").write_text("synthetic: true\n")
            (root / "OBSERVATION_SEALED.json").write_text("{}")
            digest = hashlib.sha256((root / "manifest.yml").read_bytes()).hexdigest()
            script = root / "data_owner.py"
            result = {
                "schema": "quant.raw_observation_assessment.v1",
                "manifest_sha256": digest,
                "content_snapshot_sha256": "b" * 64,
                "data_content_integrity": "passed",
                "historical_pit": "unknown",
                "derived_materialization": "absent",
                "research_ready": False,
                "time_basis": "UTC",
                "file_count": 1,
                "content_bytes": 5,
                "children": [],
            }
            script.write_text(
                'import json,sys\nassert sys.argv[1:3]==["contract","verify-observation"]\nprint('
                + repr(json.dumps(result))
                + ")\n"
            )
            adapter = {
                "kind": "raw_observation",
                "command": [sys.executable, str(script)],
                "root": str(root),
                "expected_manifest_sha256": digest,
                "max_content_bytes": 1024,
                "max_files": 10,
            }
            config = {
                "schema": "quant.orchestrator_config.v1",
                "adapters": {"raw": adapter},
                "catalog": [],
            }
            workflow = {
                "schema": "quant.workflow.v1",
                "idempotency_key": "raw-check",
                "title": "Synthetic sealed input",
                "steps": [
                    {"id": "raw", "adapter": "raw", "depends_on": [], "skills": []},
                    {
                        "id": "qualified",
                        "adapter": "raw",
                        "depends_on": ["raw"],
                        "skills": [],
                        "requires_evidence": {"raw": ["historical_pit"]},
                    },
                ],
            }
            plan = build_plan(workflow, config)
            with Store(root / "tasks.sqlite") as store:
                wid = store.submit(plan)["workflow_id"]
                store.approve(wid, plan["plan_sha256"], ["raw_observation"], "operator")
                view = Scheduler(store).tick(wid)
                self.assertEqual(view["steps"][0]["status"], "SUCCEEDED")
                self.assertEqual(
                    view["steps"][0]["evidence"]["checks"]["input_integrity"]["status"], "verified"
                )
                self.assertEqual(
                    view["steps"][0]["evidence"]["checks"]["historical_pit"]["status"], "unknown"
                )
                self.assertEqual(view["steps"][1]["status"], "BLOCKED")
                self.assertNotIn(str(root), json.dumps(view))
