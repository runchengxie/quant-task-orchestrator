"""Recovery commands publish only new targets and never execute a cutover."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.cli import main
from quant_task_orchestrator.deployment import backup_database
from quant_task_orchestrator.store import Store


class RecoveryCliTests(unittest.TestCase):
    def invoke(self, arguments, expected=0):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            result = main([str(x) for x in arguments])
        self.assertEqual(result, expected, error.getvalue())
        return json.loads((output if result == 0 else error).getvalue())

    def test_restore_requires_exact_digest_and_a_new_destination(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with Store(root / "source.sqlite"):
                pass
            backup = backup_database(root / "source.sqlite", root / "backup.sqlite")
            args = [
                "restore",
                "--source",
                root / "backup.sqlite",
                "--destination",
                root / "restored.sqlite",
                "--sha256",
                backup["sha256"],
            ]
            self.assertEqual(self.invoke(args)["integrity"], "ok")
            self.invoke(args, expected=1)
            self.assertTrue((root / "backup.sqlite").exists())

    def test_migration_check_reports_overlap_without_switching_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "request.json"
            source.write_text(
                json.dumps(
                    {
                        "schema": "quant.scheduler_migration_request.v1",
                        "old_owner": "old-timer",
                        "new_owner": "new-coordinator",
                        "old_active": True,
                        "new_active": True,
                    }
                )
            )
            result = self.invoke(["migration-check", "--input", source])
            self.assertFalse(result["ready"])
            self.assertIn("DUAL_ACTIVE_OWNERS", result["blockers"])
            self.assertFalse(result["cutover_executed"])
