import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.demo import run_demo


class DemoTests(unittest.TestCase):
    def test_isolated_runs_execute_and_preserve_pit_blocker(self):
        with tempfile.TemporaryDirectory() as root:
            first, second = run_demo(root), run_demo(root)
            self.assertNotEqual(first["run_directory"], second["run_directory"])
            self.assertTrue(Path(first["database_path"]).is_file())
            self.assertEqual(len(first["workflows"]), 2)
            for workflow in first["workflows"]:
                steps = {s["id"]: s for s in workflow["steps"]}
                self.assertEqual(steps["compute"]["status"], "SUCCEEDED")
                self.assertEqual(steps["qualification"]["status"], "BLOCKED")
                self.assertEqual(
                    steps["qualification"]["error_code"], "EVIDENCE_REQUIREMENTS_UNMET"
                )
