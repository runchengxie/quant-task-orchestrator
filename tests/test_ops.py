import hashlib
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from quant_task_orchestrator import ops
from quant_task_orchestrator.deployment import backup_database
from quant_task_orchestrator.event_inbox import enqueue_notification
from quant_task_orchestrator.store import Store


class OpsTests(unittest.TestCase):
    def test_storage_preflight_reports_low_space_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            before = list(Path(directory).iterdir())
            ok = ops.storage_assessment(directory, minimum_free_bytes=0)
            self.assertTrue(ok["ready"])
            low = ops.storage_assessment(directory, minimum_free_bytes=ok["total_bytes"] + 1)
            self.assertFalse(low["ready"])
            self.assertEqual(low["code"], "INSUFFICIENT_FREE_SPACE")
            self.assertEqual(list(Path(directory).iterdir()), before)

    def test_restore_checks_checksum_schema_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with Store(root / "source.db"):
                pass
            backup = backup_database(root / "source.db", root / "backup.db")
            with self.assertRaisesRegex(ValueError, "DIGEST"):
                ops.restore_database(root / "backup.db", root / "restore.db", "0" * 64)
            self.assertFalse((root / "restore.db").exists())
            result = ops.restore_database(root / "backup.db", root / "restore.db", backup["sha256"])
            self.assertEqual(result["integrity"], "ok")
            with self.assertRaises(FileExistsError):
                ops.restore_database(root / "backup.db", root / "restore.db", backup["sha256"])
            import sqlite3

            with closing(sqlite3.connect(root / "other.db")) as db:
                db.execute("create table unrelated(id)")
            checksum = hashlib.sha256((root / "other.db").read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "SCHEMA"):
                ops.restore_database(root / "other.db", root / "bad.db", checksum)
            self.assertFalse((root / "bad.db").exists())

    def test_uncertain_delivery_reconciles_without_resending(self):
        class Peer:
            local_only = True
            calls = 0
            receipt = None

            def lookup(self, notification_id):
                return self.receipt

            def send(self, notification_id, body):
                self.calls += 1
                self.receipt = {"notification_id": notification_id, "receipt_id": "local-1"}
                raise TimeoutError("response lost")

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.db"
            nid = enqueue_notification(
                ledger, dict(workflow_id="w", status="FAILED", plan_sha256="a"), "act"
            )["notification_id"]
            peer = Peer()
            self.assertEqual(ops.dispatch_notification(ledger, nid, peer=peer)["status"], "dry_run")
            self.assertEqual(peer.calls, 0)
            self.assertEqual(
                ops.dispatch_notification(ledger, nid, peer=peer, dry_run=False)["status"],
                "uncertain",
            )
            self.assertEqual(
                ops.dispatch_notification(ledger, nid, peer=peer, dry_run=False)["status"],
                "delivered",
            )
            self.assertEqual(peer.calls, 1)
            self.assertEqual(
                ops.dispatch_notification(ledger, nid, peer=peer, dry_run=False)["status"],
                "delivered",
            )
            self.assertEqual(peer.calls, 1)

    def test_unresolved_delivery_is_never_resent(self):
        class Peer:
            local_only = True
            calls = 0

            def lookup(self, notification_id):
                return None

            def send(self, notification_id, body):
                self.calls += 1
                raise TimeoutError()

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "ledger.db"
            nid = enqueue_notification(
                ledger, dict(workflow_id="w", status="FAILED", plan_sha256="a"), "act"
            )["notification_id"]
            peer = Peer()
            for _ in range(3):
                self.assertEqual(
                    ops.dispatch_notification(ledger, nid, peer=peer, dry_run=False)["status"],
                    "uncertain",
                )
            self.assertEqual(peer.calls, 1)
            with self.assertRaisesRegex(ValueError, "LOCAL_PEER"):
                ops.dispatch_notification(ledger, nid, peer=object(), dry_run=False)

    def test_scheduler_plan_blocks_dual_ownership(self):
        result = ops.scheduler_migration_plan(
            "legacy", "orchestrator", old_active=True, new_active=True
        )
        self.assertFalse(result["ready"])
        self.assertIn("DUAL_ACTIVE_OWNERS", result["blockers"])
        self.assertFalse(result["cutover_executed"])
        result = ops.scheduler_migration_plan(
            "legacy", "orchestrator", old_active=True, new_active=False
        )
        self.assertTrue(result["ready"])
        self.assertEqual(result["old_owner"], "legacy")
