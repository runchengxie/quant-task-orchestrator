"""Evidence/recovery are separate from compute success and expose no raw payloads."""

import json
import unittest

import test_coordinator

from quant_task_orchestrator.evidence import project_evidence
from quant_task_orchestrator.recovery import recovery_for


class WorkbenchEvidenceTests(unittest.TestCase):
    def test_compute_integrity_does_not_certify_other_dimensions(self):
        evidence = project_evidence("runtime", "RESULT_INTEGRITY_VERIFIED", {})
        self.assertEqual(evidence["checks"]["input_integrity"]["status"], "verified")
        for name in (
            "historical_pit",
            "execution_semantics",
            "independent_review",
            "economic_conclusion",
            "promotion",
        ):
            self.assertEqual(evidence["checks"][name]["status"], "unknown")

    def test_only_typed_check_fields_and_digests_survive(self):
        evidence = project_evidence(
            "data",
            "OWNER_ASSESSMENT",
            {
                "historical_pit": {
                    "status": "verified",
                    "source": "/private/location",
                    "evidence_sha256": "a" * 64,
                    "raw_data": "secret",
                },
                "input_integrity": {
                    "status": "verified",
                    "source": "quant-market-data-platform",
                    "evidence_sha256": "/private/file",
                },
                "secret_dimension": {"status": "verified"},
            },
        )
        self.assertNotIn("private", json.dumps(evidence))
        self.assertNotIn("secret", json.dumps(evidence))
        self.assertEqual(evidence["checks"]["historical_pit"]["status"], "unknown")
        self.assertEqual(evidence["checks"]["input_integrity"]["status"], "unknown")

    def test_diagnostic_conclusion_preserves_pit_and_promotion_unknowns(self):
        evidence = project_evidence("research", "DIAGNOSTIC_COMPLETED", {})
        self.assertEqual(evidence["checks"]["economic_conclusion"]["status"], "not_applicable")
        self.assertEqual(evidence["checks"]["historical_pit"]["status"], "unknown")
        self.assertEqual(evidence["checks"]["promotion"]["status"], "unknown")

    def test_recovery_actions_never_recommend_blind_submit(self):
        result = recovery_for(
            "UNKNOWN", "SUBMISSION_UNCERTAIN_NO_RECEIPT", "runtime", "NOT_VERIFIED", True
        )
        self.assertIn("lookup_original_key", result["actions"])
        self.assertNotIn("resubmit", result["actions"])
        self.assertTrue(result["requires_operator"])
        self.assertIn(
            "restore_approved_binding",
            recovery_for("BLOCKED", "OWNER_BINDING_CHANGED", "runtime", "", True)["actions"],
        )
        self.assertIn(
            "owner_review",
            recovery_for("BLOCKED", None, "research", "COMPLETED_UNVERIFIED", True)["actions"],
        )

    def test_existing_schema_is_readable_without_migration(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            wid = fixture.submit()
            # Simulate old release DB: remove all new additive auxiliary tables.
            for name in ("observations", "step_telemetry", "transitions"):
                fixture.store.db.execute("DROP TABLE IF EXISTS " + name)
            fixture.store.db.commit()
            from quant_task_orchestrator.store import Store

            with Store(fixture.store.path, readonly=True) as readonly:
                view = readonly.view(wid)
                self.assertEqual(
                    view["steps"][0]["evidence"]["checks"]["historical_pit"]["status"], "unknown"
                )
                self.assertEqual(view["steps"][0]["metrics"]["coverage"], "unavailable")
        finally:
            fixture.doCleanups()

    def test_observation_projection_and_metrics_survive_reopen(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            wid = fixture.submit()
            fixture.store.observe(
                wid,
                "compute",
                {
                    "historical_pit": {
                        "status": "missing",
                        "source": "quant-research",
                        "evidence_sha256": "a" * 64,
                    }
                },
            )
            fixture.store.record_call(wid, "compute", False, 0.25)
            fixture.store.record_call(wid, "compute", True, 0.5)
            fixture.store.set_step(wid, "compute", "RUNNING")
            from quant_task_orchestrator.store import Store

            with Store(fixture.store.path, readonly=True) as readonly:
                step = readonly.view(wid)["steps"][0]
                self.assertEqual(step["evidence"]["checks"]["historical_pit"]["status"], "missing")
                self.assertEqual(step["metrics"]["owner_calls"], 2)
                self.assertEqual(step["metrics"]["owner_errors"], 1)
                self.assertIsNone(step["metrics"]["model_cost_usd"])
                self.assertGreaterEqual(step["metrics"]["waiting_seconds"], 0)
                metrics = readonly.metrics()
                self.assertEqual(metrics["owner_calls"], 2)
                self.assertEqual(metrics["owner_errors"], 1)
        finally:
            fixture.doCleanups()

    def test_repeated_observation_does_not_emit_fake_state_transitions(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            wid = fixture.submit()
            fixture.store.set_step(wid, "compute", "RUNNING")
            before = len(fixture.store.events(wid))
            fixture.store.set_step(wid, "compute", "RUNNING")
            self.assertEqual(len(fixture.store.events(wid)), before)
        finally:
            fixture.doCleanups()

    def test_list_pagination_does_not_change_scheduler_reachability(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            wid = fixture.submit()
            self.assertEqual(len(fixture.store.list(limit=1, offset=0)), 1)
            self.assertEqual(fixture.store.list(limit=1, offset=1), [])
            self.assertIn(wid, fixture.store.scheduler_ids())
            self.assertEqual(fixture.store.pagination(1, 0)["total"], 1)
        finally:
            fixture.doCleanups()


if __name__ == "__main__":
    unittest.main()
