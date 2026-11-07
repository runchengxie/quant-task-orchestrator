"""Conformance through the coordinator, not only standalone adapter helpers."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from fixtures.asset_owner import data_fixture, report_fixture

from quant_task_orchestrator.contracts import build_plan
from quant_task_orchestrator.scheduler import Scheduler
from quant_task_orchestrator.store import Store


class MultiOwnerWorkflowTests(unittest.TestCase):
    def test_data_report_workflow_retains_owner_evidence_and_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_dir, report_dir = root / "data", root / "report"
            data_dir.mkdir()
            report_dir.mkdir()
            data, data_receipt = data_fixture(data_dir)
            report, report_receipt = report_fixture(report_dir)
            for adapter, receipt, name in (
                (data, data_receipt, "data"),
                (report, report_receipt, "report"),
            ):
                script = root / (name + "_owner.py")
                prefix = (
                    "assert sys.argv[1:3] == ['contract','assess']\n"
                    if name == "data"
                    else "assert sys.argv[1] == '--input'\n"
                )
                script.write_text(
                    "import sys\n" + prefix + "print(" + repr(json.dumps(receipt)) + ")\n"
                )
                adapter["command"] = [sys.executable, str(script)]
            config = {
                "schema": "quant.orchestrator_config.v1",
                "adapters": {"data": data, "report": report},
                "catalog": [],
            }
            workflow = {
                "schema": "quant.workflow.v1",
                "idempotency_key": "asset-workflow",
                "title": "Synthetic data to report",
                "steps": [
                    {"id": "data", "adapter": "data", "depends_on": [], "skills": []},
                    {"id": "report", "adapter": "report", "depends_on": ["data"], "skills": []},
                ],
            }
            plan = build_plan(workflow, config)
            with Store(root / "workflow.sqlite") as store:
                wid = store.submit(plan)["workflow_id"]
                store.approve(wid, plan["plan_sha256"], ["data", "report"], "operator")
                view = Scheduler(store).tick(wid)
                self.assertEqual(view["status"], "SUCCEEDED")
                self.assertEqual(
                    view["steps"][0]["evidence_status"], "PUBLICATION_METADATA_VERIFIED"
                )
                self.assertEqual(
                    view["steps"][0]["evidence"]["checks"]["input_integrity"]["status"], "unknown"
                )
                self.assertEqual(
                    view["steps"][1]["evidence"]["checks"]["input_integrity"]["status"], "verified"
                )
                self.assertEqual(store.metrics()["owner_calls"], 2)
                self.assertNotIn(str(root), json.dumps(view))
                self.assertFalse(view["research_validated"])


if __name__ == "__main__":
    unittest.main()
