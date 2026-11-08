import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.demo import run_demo
from quant_task_orchestrator.economic_cache import compare_cached, list_results
from quant_task_orchestrator.store import Store


class DemoTests(unittest.TestCase):
    def test_isolated_runs_execute_and_preserve_pit_blocker(self):
        with tempfile.TemporaryDirectory() as root:
            first, second = run_demo(root), run_demo(root)
            self.assertNotEqual(first["run_directory"], second["run_directory"])
            self.assertTrue(Path(first["database_path"]).is_file())
            self.assertEqual(len(first["workflows"]), 2)
            with Store(first["database_path"], readonly=True) as store:
                imported = list_results(store)
                self.assertEqual(imported["total"], 2)
                self.assertTrue(
                    all(x["result"]["evidence_class"] == "synthetic" for x in imported["results"])
                )
                pins = [x["snapshot_sha256"] for x in imported["results"]]
                result = compare_cached(store, *pins)
                self.assertEqual(result["status"], "comparable")
                self.assertFalse(result["research_validated"])

            for workflow in first["workflows"]:
                steps = {s["id"]: s for s in workflow["steps"]}
                self.assertEqual(steps["compute"]["status"], "SUCCEEDED")
                self.assertEqual(steps["qualification"]["status"], "BLOCKED")
                self.assertEqual(
                    steps["qualification"]["error_code"], "EVIDENCE_REQUIREMENTS_UNMET"
                )
