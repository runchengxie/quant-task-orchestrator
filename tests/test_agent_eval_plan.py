import json
import unittest
from unittest.mock import patch

from quant_task_orchestrator.agent_eval_plan import build_agent_evaluation_plan
from quant_task_orchestrator.contracts import digest
from quant_task_orchestrator.evaluation import default_suite


class AgentEvaluationPlanTests(unittest.TestCase):
    def test_static_json_plan_never_executes(self):
        with (
            patch("subprocess.run", side_effect=AssertionError("no execution")),
            patch("builtins.open", side_effect=AssertionError("no reads")),
        ):
            plan = build_agent_evaluation_plan()
        self.assertEqual(json.loads(json.dumps(plan)), plan)
        self.assertEqual(plan["schema"], "quant.agent_evaluation_plan.v1")
        self.assertEqual(plan["suite"]["sha256"], digest(default_suite()))
        self.assertEqual(len(plan["scenarios"]), 7)
        self.assertEqual([x["harness_case"] for x in plan["scenarios"]], default_suite()["cases"])

    def test_no_empty_pass_or_fabricated_measurements(self):
        plan = build_agent_evaluation_plan()
        self.assertEqual(plan["status"], "not_run")
        self.assertFalse(plan["model_evaluated"])
        self.assertTrue(plan["requires_explicit_call_budget"])
        self.assertEqual(plan["outcome"], "unknown")
        self.assertIsNone(plan["score"])
        self.assertIsNone(plan["trace"])
        self.assertNotIn("model", plan)
        self.assertTrue(all(case["outcome"] == "unknown" for case in plan["scenarios"]))
        self.assertEqual(
            plan["recommended_budget"],
            {"max_model_calls": 2, "max_sessions": 1, "max_elapsed_seconds": 300},
        )
        self.assertIn(
            "missing or empty observations cannot pass",
            plan["review"]["criteria"][-1]["requirement"],
        )

    def test_fresh_copies_and_research_identity_requirements(self):
        first = build_agent_evaluation_plan()
        first["scenarios"][0]["harness_case"]["arguments"]["handle"] = "mutated"
        second = build_agent_evaluation_plan()
        self.assertEqual(
            second["scenarios"][0]["harness_case"]["arguments"]["handle"], "wrong-handle"
        )
        self.assertEqual(
            second["research_snapshot"]["required_equal_bindings"],
            ["handle", "profile_sha256", "kind", "content_sha256"],
        )
        self.assertTrue(second["research_snapshot"]["snapshot_required"])
        self.assertIn("not historical PIT", second["research_snapshot"]["scope_rule"])
        self.assertIn("independent", second["review"]["assessor"])


if __name__ == "__main__":
    unittest.main()
