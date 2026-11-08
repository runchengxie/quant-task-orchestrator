"""Read-only comparison and shadow-history CLI operate without a coordinator DB."""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from test_asset_owners import data_fixture
from test_economic_results import receipt

from quant_task_orchestrator.cli import main


class GuidanceCliTests(unittest.TestCase):
    def invoke(self, args, expected=0):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = main(list(map(str, args)))
        self.assertEqual(code, expected, error.getvalue())
        return json.loads((output if not code else error).getvalue())

    def test_comparison_requires_exact_pins_and_no_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "result.json"
            path.write_text(json.dumps(receipt()))
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            args = [
                "compare-results",
                "--before",
                path,
                "--before-sha256",
                sha,
                "--after",
                path,
                "--after-sha256",
                sha,
            ]
            result = self.invoke(args)
            self.assertEqual(result["status"], "comparable")
            self.assertEqual(result["input_pins"]["before_sha256"], sha)
            self.assertFalse(result["provenance_verified"])
            args[-1] = "0" * 64
            self.assertEqual(self.invoke(args, expected=1)["code"], "OPERATION_REJECTED")

    def test_valid_shadow_binding_failure_is_retained_as_failed_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "schema": "quant.orchestrator_config.v1",
                        "catalog": [],
                        "adapters": {"raw": {"kind": "raw_observation"}},
                    }
                )
            )
            sha = hashlib.sha256(config.read_bytes()).hexdigest()
            with patch(
                "quant_task_orchestrator.shadow.build_plan",
                side_effect=ValueError("private locator"),
            ):
                result = self.invoke(
                    [
                        "shadow-check",
                        "--config",
                        config,
                        "--expected-config-sha256",
                        sha,
                        "--output-root",
                        root / "runs",
                    ]
                )
            self.assertEqual(result["status"], "FAILED")
            self.assertEqual(result["failure_phase"], "binding")
            self.assertNotIn("private locator", json.dumps(result))
            summary = self.invoke(
                ["shadow-history", "--root", root / "runs", "--expected-config-sha256", sha]
            )
            self.assertEqual(summary["failed_assessments"], 1)
            self.assertEqual(summary["observation_window"], "insufficient")

    def test_shadow_records_measured_time_and_cli_summary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            adapter, assessment = data_fixture(root)
            config = root / "shadow-config.json"
            config.write_text(
                json.dumps(
                    {
                        "schema": "quant.orchestrator_config.v1",
                        "adapters": {"data": adapter},
                        "catalog": [],
                    }
                )
            )
            sha = hashlib.sha256(config.read_bytes()).hexdigest()
            with patch("quant_task_orchestrator.owners.Owner.call", return_value=assessment):
                result = self.invoke(
                    [
                        "shadow-check",
                        "--config",
                        config,
                        "--expected-config-sha256",
                        sha,
                        "--output-root",
                        root / "runs",
                    ]
                )
            self.assertEqual(result["status"], "SUCCEEDED")
            self.assertIsNotNone(datetime.fromisoformat(result["observed_at"]).utcoffset())
            self.assertGreaterEqual(result["duration_seconds"], 0)
            summary = self.invoke(
                ["shadow-history", "--root", root / "runs", "--expected-config-sha256", sha]
            )
            self.assertEqual(summary["matched_assessments"], 1)
            self.assertEqual(summary["observation_window"], "insufficient")
            self.assertEqual(summary["measured_latency"]["samples"], 1)
            self.assertFalse(summary["production_schedule_changed"])
            self.assertNotIn(str(root), json.dumps(summary))
