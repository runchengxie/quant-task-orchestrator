import unittest

from quant_task_orchestrator.evaluation import evaluate_trace, reference_trace


class EvaluationTests(unittest.TestCase):
    def test_missing_cases_are_not_passes(self):
        report = evaluate_trace(
            {"schema": "quant.agent_trace.v1", "source": "recorded", "cases": []}
        )
        self.assertEqual(report["passed"], 0)
        self.assertTrue(report["uncertainty"])
        self.assertIsNone(report["observed_tokens"])

    def test_reference_is_harness_only_and_wrong_evidence_fails(self):
        trace = reference_trace()
        report = evaluate_trace(trace)
        self.assertFalse(report["model_evaluated"])
        self.assertEqual(report["passed"], len(report["cases"]))
        trace["cases"][0]["events"][0]["result"]["code"] = "OK"
        self.assertLess(evaluate_trace(trace)["passed"], report["passed"])

    def test_forbidden_submit_and_unknown_usage_are_visible(self):
        trace = reference_trace()
        trace["cases"][0]["events"].append({"tool": "submit", "arguments": {}, "result": {}})
        result = evaluate_trace(trace)
        self.assertEqual(result["forbidden_calls"], 1)
        self.assertIsNone(result["observed_tokens"])
        self.assertLess(result["passed"], len(result["cases"]))

    def test_budget_identity_and_evidence_are_independent_failures(self):
        for case_id, mutation, criterion in [
            ("bounded_calls", "duplicate", "call_budget"),
            ("recovery_identity", "identity", "required_observation"),
            ("missing_evidence", "missing", "required_observation"),
        ]:
            with self.subTest(case_id=case_id):
                trace = reference_trace()
                case = next(c for c in trace["cases"] if c["id"] == case_id)
                if mutation == "duplicate":
                    case["events"] *= 2
                elif mutation == "identity":
                    case["events"][0]["result"]["handle"] = "different"
                else:
                    del case["events"][0]["result"]["historical_pit"]
                result = next(c for c in evaluate_trace(trace)["cases"] if c["id"] == case_id)
                self.assertFalse(result["passed"])
                self.assertIn(criterion, result["missing_evidence"])

    def test_observed_usage_and_declared_provenance(self):
        trace = reference_trace()
        trace.update(source="recorded", model="Codex")
        for case in trace["cases"]:
            case["events"][0].update(
                usage={"total_tokens": 3}, tool_failed=True, human_takeover=True
            )
        report = evaluate_trace(trace)
        self.assertEqual(report["observed_tokens"], 21)
        self.assertEqual(report["tool_failures"], 7)
        self.assertEqual(report["human_takeovers"], 7)
        self.assertFalse(report["provenance_verified"])
        self.assertFalse(report["model_evaluated"])

    def test_unknown_case_cannot_hide_forbidden_calls(self):
        trace = reference_trace()
        trace["cases"].append(
            {"id": "unscored", "events": [{"tool": "submit", "arguments": {}, "result": {}}]}
        )
        with self.assertRaisesRegex(ValueError, "UNKNOWN_TRACE_CASE"):
            evaluate_trace(trace)

    def test_invalid_envelope_and_raw_model_are_rejected(self):
        for change in (
            {"schema": "wrong"},
            {"schema": None},
            {"source": []},
            {"source": "unknown"},
            {"model": {"secret": "raw"}},
            {"model": "a" * 161},
            {"model": "Codex\nprivate"},
            {"extra": "raw"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                evaluate_trace({**reference_trace(), **change})
        trace = reference_trace()
        del trace["schema"]
        with self.assertRaises(ValueError):
            evaluate_trace(trace)

    def test_bad_case_and_event_types_raise_value_error(self):
        for field, value in [("id", []), ("events", {})]:
            trace = reference_trace()
            trace["cases"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                evaluate_trace(trace)
        for field, value in [
            ("tool", []),
            ("arguments", []),
            ("result", []),
            ("tool_failed", "yes"),
            ("human_takeover", 1),
            ("usage", {"total_tokens": True}),
            ("unknown", "raw"),
        ]:
            trace = reference_trace()
            trace["cases"][0]["events"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                evaluate_trace(trace)

    def test_only_fixed_validated_suite_is_comparable(self):
        from quant_task_orchestrator.evaluation import default_suite

        for suite in ([], {}, {"schema": "quant.agent_evaluation_suite.v1"}):
            with self.subTest(suite=suite), self.assertRaises(ValueError):
                evaluate_trace(reference_trace(), suite)
        for field, value in [
            ("id", []),
            ("max_calls", 0),
            ("max_calls", True),
            ("max_calls", 1001),
            ("arguments", []),
            ("tool", []),
        ]:
            suite = default_suite()
            suite["cases"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                evaluate_trace(reference_trace(), suite)
        suite = default_suite()
        suite["cases"].append(suite["cases"][0])
        with self.assertRaises(ValueError):
            evaluate_trace(reference_trace(), suite)
        suite = default_suite()
        suite["cases"][0]["max_calls"] = 2
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_EVALUATION_SUITE"):
            evaluate_trace(reference_trace(), suite)
        self.assertEqual(evaluate_trace(reference_trace(), default_suite())["passed"], 7)
