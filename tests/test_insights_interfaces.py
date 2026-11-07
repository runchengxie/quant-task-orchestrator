"""Read-only insights APIs and explicitly mutating local import commands."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.cli import main


class InsightsCliTests(unittest.TestCase):
    def invoke(self, arguments):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main([str(x) for x in arguments]), 0)
        return json.loads(output.getvalue())

    def test_public_demo_compare_impact_and_reference_evaluation(self):
        with tempfile.TemporaryDirectory() as temporary:
            info = self.invoke(["demo", "--output-root", temporary])
            db = info["database_path"]
            before, after = info["workflow_ids"]
            compared = self.invoke(["--database", db, "compare", before, after])
            self.assertEqual(compared["schema"], "quant.workflow_comparison.v1")
            self.assertEqual(compared["economic_comparison"]["status"], "unavailable")
            report = self.invoke(["--database", db, "eval-trace", "--reference"])
            self.assertFalse(report["model_evaluated"])
            self.assertEqual(report["evaluation_scope"], "reference-not-model")
            listed = self.invoke(["--database", db, "evaluations"])
            self.assertTrue(listed["reports"])
            proposal = Path(temporary) / "proposal.json"
            proposal.write_text(
                json.dumps(
                    {
                        "schema": "quant.change_proposal.v1",
                        "kind": "pinned_input",
                        "previous": "a" * 64,
                        "next": "b" * 64,
                    }
                )
            )
            impact = self.invoke(["--database", db, "impact", "--proposal", proposal])
            self.assertFalse(impact["execution_authorized"])
