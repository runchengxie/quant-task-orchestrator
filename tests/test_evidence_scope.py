"""Market applicability and proof freshness are different clocks."""

import copy
import unittest
from datetime import UTC, datetime

from quant_task_orchestrator.evidence import project_evidence
from quant_task_orchestrator.evidence_scope import assess_check, validate_context

CONTEXT = {
    "data_sha256": "a" * 64,
    "strategy_sha256": "b" * 64,
    "universe_sha256": "c" * 64,
    "as_of": "2020-12-31T16:00:00Z",
    "sample_start": "2020-01-01",
    "sample_end": "2020-12-31",
}


class EvidenceScopeTests(unittest.TestCase):
    def check(self):
        return {
            "status": "verified",
            "source": "quant-research",
            "evidence_sha256": "d" * 64,
            "scope": copy.deepcopy(CONTEXT),
            "assessed_at": "2026-11-01T00:00:00Z",
            "valid_until": "2026-11-10T00:00:00Z",
        }

    def test_retrospective_assessment_can_match_historical_market_scope(self):
        validate_context(CONTEXT)
        result = assess_check(self.check(), CONTEXT, now=datetime(2026, 11, 8, tzinfo=UTC))
        self.assertTrue(result["usable"])
        self.assertEqual(result["code"], "APPLICABLE")

    def test_expiry_missing_scope_identity_and_sample_bounds_fail_closed(self):
        variants = [
            {**self.check(), "valid_until": "2026-11-08T00:00:00Z"},
            {k: v for k, v in self.check().items() if k != "scope"},
            {**self.check(), "scope": {**CONTEXT, "strategy_sha256": "e" * 64}},
            {**self.check(), "scope": {**CONTEXT, "sample_start": "2020-06-01"}},
            {**self.check(), "assessed_at": "2026-11-09T00:00:00Z"},
        ]
        for check in variants:
            with self.subTest(check=check):
                self.assertFalse(
                    assess_check(check, CONTEXT, now=datetime(2026, 11, 8, tzinfo=UTC))["usable"]
                )

    def test_public_projection_keeps_safe_scope_but_never_private_fields(self):
        check = {**self.check(), "private_path": "/private/secret"}
        projected = project_evidence("research", "SUPPORTED", {"historical_pit": check})["checks"][
            "historical_pit"
        ]
        self.assertIn("scope", projected)
        self.assertNotIn("private_path", projected)
        self.assertEqual(projected["status"], "verified")
        self.assertFalse(
            project_evidence("research", "SUPPORTED", {"promotion": check})["checks"]["promotion"]
            .get("applicability", {})
            .get("usable", False)
        )

    def test_scoped_runtime_claim_cannot_impersonate_research_authority(self):
        projected = project_evidence(
            "runtime", "RESULT_INTEGRITY_VERIFIED", {"historical_pit": self.check()}
        )["checks"]["historical_pit"]
        self.assertFalse(
            assess_check(
                projected,
                CONTEXT,
                now=datetime(2026, 11, 8, tzinfo=UTC),
                dimension="historical_pit",
            )["usable"]
        )

    def test_scoped_pit_requires_an_appropriate_owner(self):
        check = {**self.check(), "source": "quant-backtest-runtime"}
        result = assess_check(
            check, CONTEXT, now=datetime(2026, 11, 8, tzinfo=UTC), dimension="historical_pit"
        )
        self.assertFalse(result["usable"])
        self.assertEqual(result["code"], "UNSUITABLE_AUTHORITY")

    def test_malformed_owner_observation_cannot_restore_runtime_legacy_baseline(self):
        for change in ({"evidence_sha256": "not-a-hash"}, {"source": ["bad"]}, {"status": []}):
            raw = {**self.check(), "valid_until": "2026-01-01T00:00:00Z", **change}
            projected = project_evidence(
                "runtime", "RESULT_INTEGRITY_VERIFIED", {"input_integrity": raw}
            )["checks"]["input_integrity"]
            self.assertFalse(assess_check(projected)["usable"])
            self.assertNotEqual(projected["status"], "verified")

    def test_partial_or_unknown_context_and_naive_time_are_invalid(self):
        for value in (
            {},
            {**CONTEXT, "as_of": "2020-12-31"},
            {**CONTEXT, "private_path": "secret"},
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_context(value)


class ScopedSchedulerTests(unittest.TestCase):
    def run_gate(self, change=None, scoped=True):
        from unittest.mock import patch

        import test_coordinator

        from quant_task_orchestrator.scheduler import Scheduler

        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            step = {
                "id": "audit",
                "adapter": "compute",
                "depends_on": ["compute"],
                "skills": [],
                "requires_evidence": {"compute": ["input_integrity"]},
            }
            if scoped:
                step["evidence_context"] = copy.deepcopy(CONTEXT)
            fixture.workflow["steps"].append(step)
            wid = fixture.submit()
            fixture.store.set_step(
                wid,
                "compute",
                "SUCCEEDED",
                owner_id="upstream",
                evidence="RESULT_INTEGRITY_VERIFIED",
            )
            claim = {**EvidenceScopeTests().check(), "source": "quant-backtest-runtime"}
            if change:
                claim.update(change)
            fixture.store.observe(wid, "compute", {"input_integrity": claim})

            def at_fixed_time(check, context=None, **kwargs):
                return assess_check(check, context, now=datetime(2026, 11, 8, tzinfo=UTC), **kwargs)

            with patch("quant_task_orchestrator.scheduler.assess_check", side_effect=at_fixed_time):
                result = Scheduler(fixture.store).tick(wid)
            return result
        finally:
            fixture.doCleanups()

    def test_matching_fresh_evidence_allows_dependent_dispatch(self):
        self.assertEqual(self.run_gate()["steps"][1]["status"], "SUCCEEDED")

    def test_expired_and_mismatched_claims_block_new_dispatch_not_old_history(self):
        for change in (
            {"valid_until": "2026-11-08T00:00:00Z"},
            {"scope": {**CONTEXT, "data_sha256": "e" * 64}},
        ):
            view = self.run_gate(change)
            self.assertEqual(view["steps"][0]["status"], "SUCCEEDED")
            self.assertEqual(
                view["steps"][0]["evidence"]["checks"]["input_integrity"]["status"], "verified"
            )
            self.assertEqual(view["steps"][1]["status"], "BLOCKED")
            self.assertEqual(view["steps"][1]["error_code"], "EVIDENCE_REQUIREMENTS_UNMET")

    def test_expired_temporal_metadata_also_blocks_an_unscoped_legacy_gate(self):
        self.assertEqual(
            self.run_gate({"valid_until": "2026-11-08T00:00:00Z"}, scoped=False)["steps"][1][
                "status"
            ],
            "BLOCKED",
        )
