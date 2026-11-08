"""Declared financial differences require an identical, fully known comparison basis."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.economic_results import compare_results, load_result


def receipt():
    return {
        "schema": "quant.economic_result.v1",
        "owner": "quant-research",
        "source_revision": "a" * 40,
        "result_id": "b" * 64,
        "report_sha256": "c" * 64,
        "evidence_class": "synthetic",
        "execution_status": "succeeded",
        "admission_status": "blocked",
        "basis": dict.fromkeys(
            [
                "data_sha256",
                "universe_sha256",
                "benchmark_sha256",
                "cost_model_sha256",
                "execution_semantics_sha256",
                "metric_definitions_sha256",
            ],
            "d" * 64,
        )
        | {
            "sample_start": "2025-01-01",
            "sample_end": "2025-12-31",
            "time_zone": "UTC",
            "currency": "USD",
            "return_frequency": "daily",
            "history_visibility": "seen",
        },
        "metrics": {
            "total_return": 0.10,
            "annualized_return": 0.10,
            "max_drawdown": 0.05,
            "annualized_volatility": 0.15,
            "sharpe": 0.7,
            "turnover": 1.2,
        },
    }


class EconomicResultTests(unittest.TestCase):
    def test_matching_basis_computes_ratios_without_financial_authority(self):
        before = receipt()
        after = copy.deepcopy(before)
        after["metrics"]["total_return"] = 0.12
        result = compare_results(before, after)
        self.assertEqual(result["status"], "comparable")
        self.assertAlmostEqual(result["metrics"]["total_return"]["delta"], 0.02)
        self.assertFalse(result["provenance_verified"])
        self.assertFalse(result["promotion_authorized"])
        self.assertFalse(result["research_validated"])

    def test_every_unknown_or_different_basis_blocks_even_two_unknowns(self):
        for key in receipt()["basis"]:
            left = receipt()
            right = receipt()
            left["basis"][key] = right["basis"][key] = None
            result = compare_results(left, right)
            self.assertEqual(result["status"], "not_comparable", key)
            self.assertIn("MISSING_BASIS:" + key, result["reasons"])
            self.assertEqual(result["metrics"], {})
        right = receipt()
        right["basis"]["cost_model_sha256"] = "e" * 64
        self.assertIn(
            "BASIS_MISMATCH:cost_model_sha256", compare_results(receipt(), right)["reasons"]
        )

    def test_unknown_metric_is_not_zero_and_drawdown_is_positive_fraction(self):
        right = receipt()
        right["metrics"]["sharpe"] = None
        self.assertIsNone(compare_results(receipt(), right)["metrics"]["sharpe"]["delta"])
        for bad in [-0.2, 1.01, True, float("nan"), float("inf")]:
            right = receipt()
            right["metrics"]["max_drawdown"] = bad
            with self.assertRaises(ValueError):
                compare_results(receipt(), right)
        right = receipt()
        right["metrics"] = {key: None for key in right["metrics"]}
        self.assertIn("MISSING_METRIC_PAIRS", compare_results(receipt(), right)["reasons"])
        right = receipt()
        right["metrics"]["total_return"] = -1.01
        with self.assertRaises(ValueError):
            compare_results(receipt(), right)

    def test_unsuccessful_execution_and_mixed_evidence_do_not_compare(self):
        right = receipt()
        right["execution_status"] = "failed"
        self.assertEqual(compare_results(receipt(), right)["status"], "not_comparable")
        right = receipt()
        right["evidence_class"] = "historical_mechanism"
        self.assertEqual(compare_results(receipt(), right)["status"], "not_comparable")

    def test_strict_bounded_pinned_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "result.json"
            path.write_text(json.dumps(receipt()))
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(load_result(path, sha), receipt())
            with self.assertRaises(ValueError):
                load_result(path, "0" * 64)
            link = Path(tmp) / "link"
            link.symlink_to(path)
            with self.assertRaises((ValueError, OSError)):
                load_result(link, sha)
            for payload in [b'{"schema":1,"schema":2}', b'{"x":NaN}', b"x" * 1_048_577]:
                path.write_bytes(payload)
                with self.assertRaises(ValueError):
                    load_result(path, hashlib.sha256(payload).hexdigest())

    def test_extra_keys_or_bad_shapes_fail_closed(self):
        for mutate in [
            lambda r: r.update(private_path="/secret"),
            lambda r: r["basis"].update(extra="value"),
            lambda r: r["metrics"].update(extra=1),
            lambda r: r["basis"].update(sample_start="2026-01-01"),
            lambda r: r["basis"].update(time_zone="Not/AZone"),
            lambda r: r.update(evidence_class=[]),
            lambda r: r["basis"].update(return_frequency=[]),
        ]:
            right = receipt()
            mutate(right)
            with self.assertRaises(ValueError):
                compare_results(receipt(), right)
