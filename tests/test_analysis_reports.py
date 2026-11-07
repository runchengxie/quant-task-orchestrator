"""Derived evaluation cache cannot introduce extra payloads or a model verdict."""

import json
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.analysis_reports import list_evaluations, record_evaluation
from quant_task_orchestrator.contracts import digest
from quant_task_orchestrator.evaluation import reference_trace
from quant_task_orchestrator.store import Store


class EvaluationCacheTests(unittest.TestCase):
    def test_recorded_reference_and_strict_cache_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            with Store(Path(directory) / "state.sqlite") as store:
                report = record_evaluation(store, reference_trace())
                self.assertFalse(list_evaluations(store)["reports"][0]["model_evaluated"])
                raw = json.dumps(report).replace(
                    '"schema": "quant.agent_evaluation.v1"',
                    '"schema":"wrong","schema":"quant.agent_evaluation.v1"',
                )
                store.db.execute("UPDATE evaluation_reports SET payload=?", (raw,))
                with self.assertRaises(ValueError):
                    list_evaluations(store)

    def test_extra_cache_fields_are_never_projected(self):
        with tempfile.TemporaryDirectory() as directory:
            with Store(Path(directory) / "state.sqlite") as store:
                report = record_evaluation(store, reference_trace())
                report["raw_private_payload"] = "/private/secret"
                store.db.execute(
                    "UPDATE evaluation_reports SET report_sha256=?,payload=?",
                    (digest(report), json.dumps(report)),
                )
                with self.assertRaises(ValueError):
                    list_evaluations(store)

    def test_nested_payload_types_scores_and_uncertainty_fail_closed(self):
        import copy

        mutations = [
            lambda r: r["cases"][0].update(raw_private_payload="/private/secret"),
            lambda r: r["cases"][0]["criteria"].update(raw_private_payload="/private/secret"),
            lambda r: r["cases"][0].update(missing_evidence=["/private/secret"]),
            lambda r: r.update(reported_model={"prompt": "/private/secret"}),
            lambda r: r.update(reported_model="x" * 161),
            lambda r: r.update(uncertainty=["/private/secret"]),
            lambda r: r.update(passed=999),
            lambda r: r["cases"][0].update(passed=False),
            lambda r: r["cases"][0]["criteria"].update(call_budget=1),
            lambda r: r["cases"][0].update(id=[]),
            lambda r: r.update(unknown_usage_events=-1),
            lambda r: r.update(observed_tokens=0),
            lambda r: r.update(tool_calls=0),
            lambda r: r.update(suite_version="private-version"),
            lambda r: r.update(unknown_cases=["hidden"]),
        ]
        with tempfile.TemporaryDirectory() as directory:
            with Store(Path(directory) / "state.sqlite") as store:
                baseline = record_evaluation(store, reference_trace())
                for mutation in mutations:
                    report = copy.deepcopy(baseline)
                    mutation(report)
                    store.db.execute("DELETE FROM evaluation_reports")
                    store.db.execute(
                        "INSERT INTO evaluation_reports VALUES(?,?)",
                        (digest(report), json.dumps(report)),
                    )
                    with self.subTest(report=report), self.assertRaises(ValueError):
                        list_evaluations(store)

    def test_valid_partial_and_complete_usage_reports_roundtrip(self):
        traces = [
            reference_trace(),
            {"schema": "quant.agent_trace.v1", "source": "recorded", "cases": []},
        ]
        known = reference_trace()
        for case in known["cases"]:
            case["events"][0]["usage"] = {"total_tokens": 3}
        traces.append(known)
        partial = reference_trace()
        partial["cases"] = partial["cases"][:1]
        partial["cases"][0]["events"][0]["usage"] = {"total_tokens": 3}
        traces.append(partial)
        forbidden = reference_trace()
        forbidden["cases"][0]["events"].append({"tool": "submit", "arguments": {}, "result": {}})
        traces.append(forbidden)
        empty_case = reference_trace()
        empty_case["cases"][0]["events"] = []
        for case in empty_case["cases"]:
            for event in case["events"]:
                event["usage"] = {"total_tokens": 0}
        traces.append(empty_case)
        with tempfile.TemporaryDirectory() as directory:
            with Store(Path(directory) / "state.sqlite") as store:
                for trace in traces:
                    expected = record_evaluation(store, trace)
                    self.assertEqual(list_evaluations(store)["reports"][0], expected)
