"""Publication hints wake only already approved, identity-frozen workflows."""

import json
import unittest

import test_coordinator

from quant_task_orchestrator.scheduler import Scheduler


class EventTriggerTests(unittest.TestCase):
    def test_data_publication_hint_requires_frozen_source_and_owner_revalidation(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            fixture.workflow["trigger"] = {
                "source": "quant-market-data-platform",
                "event_type": "data.published",
            }
            wid = fixture.submit()
            self.assertEqual(Scheduler(fixture.store).tick(wid)["status"], "AWAITING_EVENT")
            self.assertEqual(json.loads(fixture.owner_state.read_text())["submissions"], 0)
            event = {
                "schema": "quant.workflow_event.v1",
                "event_id": "publication-1",
                "workflow_id": wid,
                "source": "unrelated-owner",
                "type": "data.published",
            }
            fixture.store.hint(event)
            self.assertEqual(Scheduler(fixture.store).tick(wid)["status"], "AWAITING_EVENT")
            fixture.store.hint(
                {**event, "event_id": "publication-2", "source": "quant-market-data-platform"}
            )
            self.assertEqual(Scheduler(fixture.store).tick(wid)["status"], "SUCCEEDED")
            self.assertEqual(json.loads(fixture.owner_state.read_text())["submissions"], 1)
        finally:
            fixture.doCleanups()

    def test_matching_event_never_approves_unapproved_workflow(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            fixture.workflow["trigger"] = {
                "source": "quant-intel-platform",
                "event_type": "report.published",
            }
            wid = fixture.submit(False)
            fixture.store.hint(
                {
                    "schema": "quant.workflow_event.v1",
                    "event_id": "report-1",
                    "workflow_id": wid,
                    "source": "quant-intel-platform",
                    "type": "report.published",
                }
            )
            self.assertEqual(Scheduler(fixture.store).tick(wid)["status"], "AWAITING_APPROVAL")
            self.assertEqual(json.loads(fixture.owner_state.read_text())["submissions"], 0)
        finally:
            fixture.doCleanups()
