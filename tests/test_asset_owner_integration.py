"""Opt-in real installed Owners using temporary synthetic metadata only."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.asset_owners import bind_asset, grade_asset, start_asset

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from asset_owner import data_fixture, report_fixture


class InstalledAssetOwners(unittest.TestCase):
    def acceptance(self, variable, builder):
        command = os.environ.get(variable)
        if not command:
            self.skipTest(variable + " is not configured")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            adapter, _ = builder(root)
            adapter["command"] = [command]
            before = {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            binding = bind_asset(adapter)
            receipt = start_asset(binding)
            self.assertEqual(grade_asset(binding, receipt)[0], "SUCCEEDED")
            self.assertEqual(
                before, {str(p): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            )
            return binding, receipt

    def test_data_owner(self):
        self.acceptance("QUANT_DATA_OWNER_CLI", data_fixture)

    def test_report_owner(self):
        self.acceptance("QUANT_REPORT_OWNER_CLI", report_fixture)

    def test_report_owner_rejects_wrong_manifest_hash(self):
        command = os.environ.get("QUANT_REPORT_OWNER_CLI")
        if not command:
            self.skipTest("QUANT_REPORT_OWNER_CLI is not configured")
        import json

        from quant_task_orchestrator.owners import OwnerError

        with tempfile.TemporaryDirectory() as directory:
            adapter, _ = report_fixture(Path(directory))
            adapter["command"] = [command]
            manifest = Path(adapter["manifest"])
            payload = json.loads(manifest.read_text())
            payload["report_sha256"] = "0" * 64
            manifest.write_text(json.dumps(payload))
            with self.assertRaises(OwnerError):
                bind_asset(adapter)

    def test_data_owner_incomplete_publication_blocks(self):
        command = os.environ.get("QUANT_DATA_OWNER_CLI")
        if not command:
            self.skipTest("QUANT_DATA_OWNER_CLI is not configured")
        with tempfile.TemporaryDirectory() as directory:
            adapter, _ = data_fixture(Path(directory))
            adapter["command"] = [command]
            (Path(directory) / "daily-v1" / "manifest.yml").write_text(
                "dataset: daily\nstatus: running\n"
            )
            binding = bind_asset(adapter)
            receipt = start_asset(binding)
            self.assertEqual(grade_asset(binding, receipt)[0], "BLOCKED")
