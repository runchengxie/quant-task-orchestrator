"""A data readiness shadow never gains compute or notification authority."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quant_task_orchestrator.shadow import run_shadow


class ShadowTests(unittest.TestCase):
    def test_mutating_kind_is_rejected_before_owner_or_output_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "schema": "quant.orchestrator_config.v1",
                        "adapters": {"engine": {"kind": "runtime", "command": ["/not/an/owner"]}},
                        "catalog": [],
                    }
                )
            )
            sha = hashlib.sha256(config.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "READ_ONLY_DATA"):
                run_shadow(config, sha, root / "outputs")
            self.assertFalse((root / "outputs").exists())

    def test_approved_bytes_are_parsed_without_reopening_text_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config.json"
            config.write_bytes(
                b'{"schema":"quant.orchestrator_config.v1","adapters":{},"catalog":[]}'
            )
            sha = hashlib.sha256(config.read_bytes()).hexdigest()
            with patch.object(Path, "read_text", side_effect=AssertionError("racy reopen")):
                with self.assertRaisesRegex(ValueError, "READ_ONLY_DATA"):
                    run_shadow(config, sha, root / "outputs")

    def test_changed_config_is_rejected_without_creating_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "config.json"
            config.write_text("{}")
            with self.assertRaisesRegex(ValueError, "CONFIG_CHANGED"):
                run_shadow(config, "0" * 64, root / "outputs")
            self.assertFalse((root / "outputs").exists())
