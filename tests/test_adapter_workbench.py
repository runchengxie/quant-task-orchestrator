"""Registry/contract and evidence gates apply before new Owner dispatch."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

import test_coordinator

from quant_task_orchestrator.adapters import adapter_catalog
from quant_task_orchestrator.contracts import build_plan
from quant_task_orchestrator.scheduler import Scheduler
from quant_task_orchestrator.store import Store


class AdapterWorkbenchTests(unittest.TestCase):
    def test_registry_lists_effects_without_granting_authority(self):
        catalog = adapter_catalog()
        self.assertFalse(catalog["permission_grant"])
        self.assertEqual(
            {row["kind"] for row in catalog["adapters"]},
            {
                "runtime",
                "research",
                "data",
                "report",
                "native_session",
                "codex_task",
                "raw_observation",
            },
        )
        self.assertEqual(
            next(row for row in catalog["adapters"] if row["kind"] == "native_session")["effects"],
            [],
        )

    def test_optional_owner_revision_is_pinned_and_projected(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            fixture.config["adapters"]["compute"]["owner_revision"] = "a" * 40
            wid = fixture.submit()
            self.assertEqual(fixture.store.view(wid)["steps"][0]["owner_revision"], "a" * 40)
            fixture.config["adapters"]["compute"]["owner_revision"] = "latest"
            with self.assertRaises(ValueError):
                fixture.plan()
        finally:
            fixture.doCleanups()

    def test_unverified_pit_prevents_dependent_compute(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            fixture.workflow["steps"].append(
                {
                    "id": "qualified",
                    "adapter": "compute",
                    "depends_on": ["compute"],
                    "skills": [],
                    "requires_evidence": {"compute": ["historical_pit"]},
                }
            )
            wid = fixture.submit()
            Scheduler(fixture.store).tick(wid)
            view = fixture.store.view(wid)
            self.assertEqual(view["steps"][1]["status"], "BLOCKED")
            self.assertEqual(view["steps"][1]["error_code"], "EVIDENCE_REQUIREMENTS_UNMET")
            self.assertIsNone(view["steps"][1]["owner_id"])
        finally:
            fixture.doCleanups()

    def test_native_session_matches_config_receipt_events_and_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config, receipt, events = (
                root / "config.json",
                root / "receipt.json",
                root / "events.jsonl",
            )
            config.write_text("{}")
            receipt.write_text("{}")
            events.write_text("{}\n")
            script = root / "owner.py"
            script.write_text("""import hashlib,json,pathlib,sys
args=sys.argv[1:]; p=lambda key:pathlib.Path(args[args.index(key)+1])
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
print(json.dumps({'schema':'quant.native_research_session_inspection.v1','session_id':args[args.index('--session')+1],
'config_sha256':sha(p('--config')),'receipt_sha256':sha(p('--receipt')),'events_sha256':sha(p('--events')),
'execution_complete':True,'execution_status':'complete','observed_tools':['context','report'],
'wall_seconds':2.5,'model_cost_usd':None,'research_validated':False,'promotion_authorized':False}))
""")
            config_map = {
                "schema": "quant.orchestrator_config.v1",
                "catalog": [],
                "adapters": {
                    "session": {
                        "kind": "native_session",
                        "command": [sys.executable, str(script)],
                        "config": str(config),
                        "receipt": str(receipt),
                        "events": str(events),
                        "session_id": "synthetic-session",
                    }
                },
            }
            workflow = {
                "schema": "quant.workflow.v1",
                "idempotency_key": "session-workflow",
                "title": "Synthetic native session",
                "steps": [{"id": "session", "adapter": "session", "depends_on": [], "skills": []}],
            }
            plan = build_plan(workflow, config_map)
            with Store(root / "workflow.sqlite") as store:
                wid = store.submit(plan)["workflow_id"]
                store.approve(wid, plan["plan_sha256"], ["native_session"], "operator")
                view = Scheduler(store).tick(wid)
                self.assertEqual(view["status"], "SUCCEEDED")
                self.assertFalse(view["promotion_authorized"])
                self.assertEqual(view["steps"][0]["owner_id"], "synthetic-session")
                self.assertNotIn(str(root), json.dumps(view))
                self.assertIsNone(view["steps"][0]["metrics"]["model_cost_usd"])

    def test_restored_pre_dispatch_binding_does_not_bypass_pit_gate(self):
        from unittest.mock import patch

        import quant_task_orchestrator.scheduler as scheduling

        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            fixture.workflow["steps"].append(
                {
                    "id": "qualified",
                    "adapter": "compute",
                    "depends_on": ["compute"],
                    "skills": [],
                    "requires_evidence": {"compute": ["historical_pit"]},
                }
            )
            wid = fixture.submit()
            real = scheduling.verify_bindings
            calls = []

            def changed(plan):
                calls.append(1)
                if len(calls) == 2:
                    raise ValueError("OWNER_BINDING_CHANGED")
                return real(plan)

            with patch.object(scheduling, "verify_bindings", changed):
                Scheduler(fixture.store).tick(wid)
            view = Scheduler(fixture.store).tick(wid)
            self.assertEqual(view["steps"][1]["status"], "BLOCKED")
            self.assertIsNone(view["steps"][1]["owner_id"])
        finally:
            fixture.doCleanups()

    def test_observation_storage_failure_never_commits_terminal_success(self):
        import sqlite3

        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            wid = fixture.submit()
            fixture.store.db.execute(
                "CREATE TRIGGER fail_observation BEFORE INSERT ON observations BEGIN SELECT RAISE(ABORT,'synthetic storage failure'); END"
            )
            fixture.store.db.commit()
            with self.assertRaises(sqlite3.Error):
                Scheduler(fixture.store).tick(wid)
            self.assertNotEqual(fixture.store.view(wid)["steps"][0]["status"], "SUCCEEDED")
        finally:
            fixture.doCleanups()

    def test_wrong_research_identity_does_not_poison_future_reconciliation(self):
        from unittest.mock import patch

        from quant_task_orchestrator.owners import Owner

        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            campaign = fixture.root / "campaign.json"
            campaign.write_text("{}")
            fixture.config["adapters"]["compute"] = {
                "kind": "research",
                "command": [
                    sys.executable,
                    str(Path(__file__).parent / "fixtures/owner.py"),
                    str(fixture.owner_state),
                ],
                "config": str(campaign),
                "proposal_id": "proposal-1",
            }
            wid = fixture.submit()
            with patch.object(
                Owner,
                "start",
                return_value={"proposal_id": "wrong", "state": "DIAGNOSTIC_COMPLETED"},
            ):
                Scheduler(fixture.store).tick(wid)
            self.assertIsNone(fixture.store.view(wid)["steps"][0]["owner_id"])
            self.assertEqual(Scheduler(fixture.store).tick(wid)["status"], "SUCCEEDED")
        finally:
            fixture.doCleanups()


if __name__ == "__main__":
    unittest.main()
