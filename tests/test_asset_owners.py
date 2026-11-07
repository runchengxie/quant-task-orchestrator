import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quant_task_orchestrator.asset_owners import (
    bind_asset,
    evidence_asset,
    grade_asset,
    start_asset,
)

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from asset_owner import data_fixture, report_fixture


class AssetOwnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_data_freezes_metadata_and_preserves_unknown(self):
        adapter, receipt = data_fixture(self.root)
        with patch("quant_task_orchestrator.owners.Owner.call", return_value=receipt):
            binding = bind_asset(adapter)
            result = start_asset(binding)
        self.assertEqual(grade_asset(binding, result)[0], "SUCCEEDED")
        evidence = evidence_asset(binding, result)
        self.assertEqual(evidence["input_integrity"]["status"], "unknown")
        self.assertEqual(evidence["historical_pit"]["status"], "unknown")
        self.assertNotIn(str(self.root), json.dumps(evidence))
        Path(receipt["snapshot"]["assets"][0]["manifest_path"]).write_text("changed")
        with self.assertRaisesRegex(ValueError, "OWNER_BINDING_CHANGED"):
            start_asset(binding)

    def test_failed_data_check_blocks_even_successful_exit(self):
        adapter, receipt = data_fixture(self.root)
        receipt["checks"][0]["outcome"] = "failed"
        with patch("quant_task_orchestrator.owners.Owner.call", return_value=receipt):
            binding = bind_asset(adapter)
        self.assertEqual(grade_asset(binding, receipt)[0], "BLOCKED")

    def test_report_identity_and_evidence(self):
        adapter, receipt = report_fixture(self.root)
        with patch("quant_task_orchestrator.owners.Owner.call", return_value=receipt):
            binding = bind_asset(adapter)
            result = start_asset(binding)
        self.assertEqual(
            grade_asset(binding, result),
            ("SUCCEEDED", receipt["artifact_hash"], "REPORT_INTEGRITY_VERIFIED"),
        )
        evidence = evidence_asset(binding, result)
        self.assertEqual(evidence["economic_conclusion"]["status"], "unknown")
        receipt["artifact_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "OWNER_IDENTITY_MISMATCH"):
            grade_asset(binding, receipt)

    def test_rejects_malformed_and_unexpected_arguments(self):
        adapter, receipt = data_fixture(self.root)
        with self.assertRaises(ValueError):
            bind_asset({**adapter, "out": str(self.root / "out")})
        with self.assertRaises(ValueError):
            bind_asset({**adapter, "target_date": "2026-10-30"})
        with patch("quant_task_orchestrator.owners.Owner.call", return_value={}):
            with self.assertRaises(ValueError):
                bind_asset(adapter)
        receipt["checks"] = []
        with patch("quant_task_orchestrator.owners.Owner.call", return_value=receipt):
            with self.assertRaises(ValueError):
                bind_asset(adapter)

    def test_freezes_input_before_owner_call(self):
        adapter, receipt = report_fixture(self.root)

        def replace(*args, **kwargs):
            Path(adapter["manifest"]).write_text("{}")
            return receipt

        with patch("quant_task_orchestrator.owners.Owner.call", side_effect=replace):
            with self.assertRaisesRegex(ValueError, "OWNER_BINDING_CHANGED"):
                bind_asset(adapter)

    def test_malformed_data_receipts_fail_closed(self):
        mutations = [
            lambda r: r.update(research_ready=True),
            lambda r: r["snapshot"].update(data_content_verified=True),
            lambda r: r["snapshot"].update(contract_sha256="0" * 64),
            lambda r: r["snapshot"].update(assets=[]),
            lambda r: r["checks"][0].update(outcome="verified"),
            lambda r: r["checks"].append(dict(r["checks"][0])),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(number=number):
                directory = self.root / str(number)
                directory.mkdir()
                adapter, receipt = data_fixture(directory)
                mutate(receipt)
                with patch("quant_task_orchestrator.owners.Owner.call", return_value=receipt):
                    with self.assertRaises(ValueError):
                        bind_asset(adapter)

    def test_unknown_freshness_blocks_and_manifest_drift_rejected(self):
        adapter, receipt = data_fixture(self.root)
        receipt["checks"][0]["outcome"] = "unknown"
        with patch("quant_task_orchestrator.owners.Owner.call", return_value=receipt):
            binding = bind_asset(adapter)
        self.assertEqual(grade_asset(binding, receipt)[0], "BLOCKED")
        receipt["snapshot"]["assets"][0]["manifest_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            grade_asset(binding, receipt)

    def test_report_input_drift_and_fixed_arguments(self):
        adapter, receipt = report_fixture(self.root)
        with patch("quant_task_orchestrator.owners.Owner.call", return_value=receipt) as call:
            binding = bind_asset(adapter)
        args = call.call_args.args[0]
        self.assertEqual(
            args,
            [
                "--input",
                adapter["input"],
                "--manifest",
                adapter["manifest"],
                "--expected-date",
                "2026-10-02",
            ],
        )
        Path(adapter["input"]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "OWNER_BINDING_CHANGED"):
            start_asset(binding)
