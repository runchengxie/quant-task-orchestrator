"""Read-only engineering comparisons and complete impact scans."""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator import insights
from quant_task_orchestrator.contracts import digest
from quant_task_orchestrator.store import Store


def plan(key="one", revision="a" * 40):
    body = {
        "schema": "quant.workflow_plan.v1",
        "workflow": {
            "idempotency_key": key,
            "title": "Synthetic",
            "steps": [
                {"id": "a", "adapter": "worker", "skills": ["skill"], "depends_on": []},
                {"id": "b", "adapter": "other", "skills": [], "depends_on": ["a"]},
            ],
        },
        "adapters": {
            "worker": {
                "kind": "runtime",
                "owner_revision": revision,
                "owner_plan_sha256": "c" * 64,
                "owner_request_sha256": "d" * 64,
                "pins": {"/private/secret": "e" * 64},
                "budgets": {"wall_seconds": 5},
            },
            "other": {"kind": "runtime", "pins": {}},
        },
        "skills": [
            {
                "id": "skill",
                "revision": "f" * 40,
                "sha256": "1" * 64,
                "source": "/private/source",
                "path": "secret.md",
                "owner_repo": "sample/owner",
                "permissions": ["read"],
                "input_contract": "in",
                "output_contract": "out",
            }
        ],
    }
    return {**body, "plan_sha256": digest(body)}


class InsightsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.tmp.name) / "db")
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.store.close)

    def submit(self, p):
        p = copy.deepcopy(p)
        p["plan_sha256"] = digest({k: v for k, v in p.items() if k != "plan_sha256"})
        return self.store.submit(p)["workflow_id"]

    def test_compare_same_and_changed_is_safe(self):
        before = self.submit(plan())
        same = insights.compare_workflows(self.store, before, before)
        self.assertTrue(all(s["status"] == "unchanged" for s in same["steps"]))
        after = self.submit(plan("two", "b" * 40))
        result = insights.compare_workflows(self.store, before, after)
        self.assertEqual(result["steps"][0]["changed_fields"], ["owner_revision"])
        self.assertEqual(result["economic_comparison"]["status"], "unavailable")
        self.assertIsNone(result["steps"][0]["before"]["observed_usage"]["model_cost_usd"])
        self.assertNotIn("/private", json.dumps(result))
        self.assertNotIn("secret.md", json.dumps(result))

    def test_added_removed_and_missing_workflow(self):
        before = self.submit(plan())
        p = plan("two")
        p["workflow"]["steps"][0]["id"] = "new"
        p["workflow"]["steps"][1]["depends_on"] = ["new"]
        result = insights.compare_workflows(self.store, before, self.submit(p))
        self.assertEqual(
            {s["id"]: s["status"] for s in result["steps"]},
            {"a": "removed", "b": "changed", "new": "added"},
        )
        with self.assertRaisesRegex(ValueError, "WORKFLOW_NOT_FOUND"):
            insights.compare_workflows(self.store, before, "missing")

    def test_full_scan_successors_and_no_writes(self):
        first = self.submit(plan())
        for i in range(105):
            self.submit(plan("other" + str(i), "b" * 40))
        changes = self.store.db.total_changes
        result = insights.impact_preview(
            self.store,
            {
                "schema": "quant.change_proposal.v1",
                "kind": "owner_revision",
                "previous": "a" * 40,
                "next": "c" * 40,
                "target": "worker",
            },
        )
        self.assertEqual(self.store.db.total_changes, changes)
        self.assertEqual(result["scan"]["workflows_scanned"], 106)
        self.assertFalse(result["scan"]["truncated"])
        self.assertEqual(
            result["affected_workflows"],
            [
                {
                    "workflow_id": first,
                    "direct_steps": ["a"],
                    "downstream_steps": ["b"],
                    "required_new_plan": True,
                    "approval_review": True,
                }
            ],
        )

    def test_proposal_validation_and_unmatched_pin(self):
        self.submit(plan())
        good = {
            "schema": "quant.change_proposal.v1",
            "kind": "pinned_input",
            "previous": "0" * 64,
            "next": "2" * 64,
        }
        self.assertEqual(insights.impact_preview(self.store, good)["affected_workflows"], [])
        for change in (
            {"next": good["previous"]},
            {"previous": "main"},
            {"path": "/private"},
            {"target": []},
            {"kind": "unknown"},
            {"kind": []},
            {"schema": "other"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                insights.impact_preview(self.store, {**good, **change})

    def test_skill_pin_and_cyclic_graph(self):
        p = plan()
        wid = self.submit(p)
        for kind, previous, next_hash in [
            ("skill_revision", "f" * 40, "2" * 40),
            ("pinned_input", "e" * 64, "2" * 64),
        ]:
            result = insights.impact_preview(
                self.store,
                {
                    "schema": "quant.change_proposal.v1",
                    "kind": kind,
                    "previous": previous,
                    "next": next_hash,
                },
            )
            self.assertEqual(result["affected_workflows"][0]["direct_steps"], ["a"])
        p["workflow"]["steps"][0]["depends_on"] = ["b"]
        self.store.db.execute("UPDATE workflows SET plan=? WHERE id=?", (json.dumps(p), wid))
        with self.assertRaisesRegex(ValueError, "CYCLIC_OR_MISSING_DEPENDENCY"):
            insights.impact_preview(
                self.store,
                {
                    "schema": "quant.change_proposal.v1",
                    "kind": "owner_revision",
                    "previous": "a" * 40,
                    "next": "c" * 40,
                },
            )

    def test_invalid_usage_stays_unknown_and_scope_changes_are_visible(self):
        self.assertIsNone(insights._number(-1))
        self.assertIsNone(insights._number(float("nan")))
        self.assertIsNone(insights._number(True))
        self.assertIsNone(insights._number(None))
        before = self.submit(plan())
        p = plan("context")
        p["workflow"]["steps"][0]["evidence_context"] = {
            "data_sha256": "1" * 64,
            "strategy_sha256": "2" * 64,
            "universe_sha256": "3" * 64,
            "as_of": "2026-01-02T00:00:00Z",
            "sample_start": "2025-01-01",
            "sample_end": "2025-12-31",
        }
        result = insights.compare_workflows(self.store, before, self.submit(p))
        self.assertIn("evidence_context", result["steps"][0]["changed_fields"])
        self.assertEqual(result["economic_comparison"]["status"], "unavailable")

    def test_context_rejects_raw_values_in_allowlisted_fields(self):
        before = self.submit(plan())
        valid = {
            "data_sha256": "1" * 64,
            "strategy_sha256": "2" * 64,
            "universe_sha256": "3" * 64,
            "as_of": "2026-01-02T00:00:00Z",
            "sample_start": "2025-01-01",
            "sample_end": "2025-12-31",
        }
        for index, invalid in enumerate(
            [
                {"data_sha256": "/private/secret"},
                {"as_of": "/private/secret"},
                {"sample_start": "/private/secret"},
                {"as_of": "2026-01-02T00:00:00+08:00"},
                {"sample_end": "2025-02-30"},
                {"data_sha256": {"prompt": "/private/secret"}},
                {"sample_start": "2026-01-01"},
                {"extra": "/private/secret"},
            ]
        ):
            with self.subTest(invalid=invalid):
                p = plan("invalid-context-" + str(index))
                p["workflow"]["steps"][0]["evidence_context"] = {**valid, **invalid}
                result = insights.compare_workflows(self.store, before, self.submit(p))
                context = result["steps"][0]["after"]["evidence_context"]
                self.assertEqual(context, {})
                self.assertNotIn("/private", json.dumps(result))

    def test_impact_snapshot_excludes_concurrent_insert_without_missing_source_ids(self):
        original_ids = {self.submit(plan("source-" + str(i))) for i in range(105)}
        original_list = self.store.list
        inserted = []

        def concurrent_list(limit=100, offset=0):
            page = original_list(limit=limit, offset=offset)
            if not inserted:
                with Store(self.store.path) as writer:
                    inserted.append(writer.submit(plan("concurrent"))["workflow_id"])
            return page

        self.store.list = concurrent_list
        result = insights.impact_preview(
            self.store,
            {
                "schema": "quant.change_proposal.v1",
                "kind": "owner_revision",
                "previous": "a" * 40,
                "next": "b" * 40,
            },
        )
        ids = [w["workflow_id"] for w in result["affected_workflows"]]
        self.assertEqual(len(ids), len(original_ids))
        self.assertEqual(set(ids), original_ids)
        self.assertNotIn(inserted[0], ids)
        self.assertEqual(result["scan"]["consistency"], "sqlite_read_snapshot")
        self.assertEqual(result["scan"]["workflows_scanned"], 105)
        self.assertFalse(self.store.db.in_transaction)

    def test_impact_preserves_caller_transaction(self):
        wid = self.submit(plan())
        self.store.db.execute("BEGIN")
        self.store.db.execute("UPDATE workflows SET cancelled=1 WHERE id=?", (wid,))
        insights.impact_preview(
            self.store,
            {
                "schema": "quant.change_proposal.v1",
                "kind": "owner_revision",
                "previous": "a" * 40,
                "next": "b" * 40,
            },
        )
        self.assertTrue(self.store.db.in_transaction)
        self.store.db.rollback()
        self.assertFalse(self.store.record(wid)["cancelled"])
