import json
import tempfile
import unittest
from pathlib import Path

import test_coordinator

from quant_task_orchestrator.event_inbox import (
    acknowledge_notification,
    consume_once,
    enqueue_notification,
    list_notifications,
)


class InboxTests(unittest.TestCase):
    def test_replay_after_receipt_loss_preserves_original_identity(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            wid = fixture.submit(False)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                inbox = root / "inbox"
                inbox.mkdir()
                event = dict(
                    schema="quant.workflow_event.v1",
                    event_id="e1",
                    workflow_id=wid,
                    source="owner",
                    type="owner.changed",
                )
                (inbox / "event.json").write_text(json.dumps(event))
                ledger = root / "journal.sqlite"
                self.assertEqual(consume_once(fixture.store, inbox, ledger)["accepted"], 1)
                ledger.unlink()  # Simulate receipt loss after the Store transaction committed.
                self.assertEqual(consume_once(fixture.store, inbox, ledger)["duplicates"], 1)
                self.assertEqual(
                    fixture.store.db.execute(
                        "SELECT COUNT(*) FROM events WHERE event_id=?", ("e1",)
                    ).fetchone()[0],
                    1,
                )
        finally:
            fixture.doCleanups()

    def test_invalid_and_symlink_files_are_quarantined_without_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inbox = root / "inbox"
            inbox.mkdir()
            (inbox / "bad.json").write_text("{secret")
            (inbox / "link.json").symlink_to(root / "missing")
            result = consume_once(None, inbox, root / "ledger.sqlite")
            self.assertEqual(result["rejected"], 2)
            self.assertNotIn("secret", json.dumps(result))

    def test_local_notifications_are_idempotent_and_acknowledged(self):
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "ledger.sqlite"
            view = dict(workflow_id="w1", status="FAILED", plan_sha256="a" * 64, steps=[])
            one = enqueue_notification(ledger, view, "inspect")
            self.assertEqual(one, enqueue_notification(ledger, view, "inspect"))
            self.assertEqual(len(list_notifications(ledger)), 1)
            acknowledge_notification(ledger, one["notification_id"])
            self.assertEqual(list_notifications(ledger), [])

    def test_conflicting_id_and_oversize_are_rejected(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            wid = fixture.submit(False)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                inbox = root / "inbox"
                inbox.mkdir()
                event = dict(
                    schema="quant.workflow_event.v1",
                    event_id="e1",
                    workflow_id=wid,
                    source="owner",
                    type="owner.changed",
                )
                fixture.store.hint(event)
                event["source"] = "other-owner"
                (inbox / "conflict.json").write_text(json.dumps(event))
                (inbox / "oversize.json").write_bytes(b" " * 16385)
                self.assertEqual(
                    consume_once(fixture.store, inbox, root / "ledger.sqlite")["rejected"], 2
                )
        finally:
            fixture.doCleanups()

    def test_crash_after_store_commit_replays_without_duplicate_effect(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            wid = fixture.submit(False)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                inbox = root / "inbox"
                inbox.mkdir()
                event = dict(
                    schema="quant.workflow_event.v1",
                    event_id="crash-event",
                    workflow_id=wid,
                    source="owner",
                    type="owner.changed",
                )
                (inbox / "event.json").write_text(json.dumps(event))

                class CrashAfterCommit:
                    def hint(self, envelope):
                        fixture.store.hint(envelope)
                        raise RuntimeError("simulated process death before journal commit")

                with self.assertRaises(RuntimeError):
                    consume_once(CrashAfterCommit(), inbox, root / "ledger.sqlite")
                self.assertEqual(
                    consume_once(fixture.store, inbox, root / "ledger.sqlite")["duplicates"], 1
                )
                self.assertEqual(
                    fixture.store.db.execute(
                        "SELECT COUNT(*) FROM events WHERE event_id=?", ("crash-event",)
                    ).fetchone()[0],
                    1,
                )
        finally:
            fixture.doCleanups()

    def test_completed_files_do_not_starve_new_event(self):
        import hashlib

        from quant_task_orchestrator.event_inbox import journal

        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            wid = fixture.submit(False)
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                inbox = root / "inbox"
                inbox.mkdir()
                event = dict(
                    schema="quant.workflow_event.v1",
                    event_id="completed",
                    workflow_id=wid,
                    source="owner",
                    type="owner.changed",
                )
                fixture.store.hint(event)
                raw = json.dumps(event).encode()
                for index in range(501):
                    (inbox / f"old-{index}.json").write_bytes(raw)
                with journal(root / "ledger.sqlite") as db:
                    db.execute(
                        "INSERT INTO receipts VALUES (?,?)",
                        (hashlib.sha256(raw).hexdigest(), "accepted"),
                    )
                event["event_id"] = "fresh-event"
                (inbox / "new.json").write_text(json.dumps(event))
                result = consume_once(fixture.store, inbox, root / "ledger.sqlite")
                self.assertEqual(result["accepted"], 1)
                self.assertEqual(result["duplicates"], 501)
                self.assertEqual(result["deferred"], 0)
        finally:
            fixture.doCleanups()
