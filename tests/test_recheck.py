"""Recorded checks never resume a blocked workflow or call an Owner."""

import copy
import json
import unittest
from unittest.mock import patch

import test_coordinator

from quant_task_orchestrator.recheck import recheck_workflow
from quant_task_orchestrator.scheduler import Scheduler


class RecheckTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_current_recorded_pit_gap_and_unchanged_authority(self):
        f = self.fixture
        second = copy.deepcopy(f.workflow["steps"][0])
        second.update(
            id="review", depends_on=["compute"], requires_evidence={"compute": ["historical_pit"]}
        )
        f.workflow["steps"].append(second)
        wid = f.submit()
        Scheduler(f.store).tick(wid)
        before = f.store.view(wid)
        events = f.store.events(wid)
        writes = f.store.db.total_changes
        with patch(
            "quant_task_orchestrator.owners.Owner.call", side_effect=AssertionError("owner called")
        ):
            result = recheck_workflow(f.store, wid)
        self.assertFalse(result["requirements_met"])
        self.assertEqual(result["blockers"][0]["dimension"], "historical_pit")
        self.assertTrue(result["new_plan_required"])
        self.assertFalse(result["owner_refresh_performed"])
        self.assertFalse(result["execution_authorized"])
        after = f.store.view(wid)
        self.assertEqual(before["status"], after["status"])
        self.assertEqual(before["plan_sha256"], after["plan_sha256"])
        self.assertEqual(
            [(s["id"], s["status"], s["owner_id"]) for s in before["steps"]],
            [(s["id"], s["status"], s["owner_id"]) for s in after["steps"]],
        )
        self.assertEqual(writes, f.store.db.total_changes)
        self.assertEqual(events, f.store.events(wid))
        self.assertNotIn(str(f.root), json.dumps(result))

    def test_no_declared_requirements_does_not_claim_qualified_research(self):
        wid = self.fixture.submit(False)
        result = recheck_workflow(self.fixture.store, wid)
        self.assertTrue(result["requirements_met"])
        self.assertEqual(result["requirements_checked"], 0)
        self.assertFalse(result["research_validated"])
        self.assertFalse(result["promotion_authorized"])
