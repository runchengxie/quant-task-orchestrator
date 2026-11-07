"""Opt-in retained native evidence through the installed Owner; no model call."""

import os
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.contracts import build_plan, read_json
from quant_task_orchestrator.scheduler import Scheduler
from quant_task_orchestrator.store import Store


@unittest.skipUnless(
    os.environ.get("QUANT_NATIVE_OWNER_CONFIG"),
    "explicit installed native inspection config required",
)
class InstalledNativeOwnerTests(unittest.TestCase):
    def test_retained_session_identity_is_verified_but_never_certifies_pit(self):
        config = read_json(os.environ["QUANT_NATIVE_OWNER_CONFIG"])
        aliases = [
            name
            for name, binding in config["adapters"].items()
            if binding["kind"] == "native_session"
        ]
        self.assertEqual(len(aliases), 1)
        alias = aliases[0]
        workflow = {
            "schema": "quant.workflow.v1",
            "idempotency_key": "native-owner-integration",
            "title": "Retained native inspection",
            "steps": [
                {"id": "session", "adapter": alias, "depends_on": [], "skills": []},
                {
                    "id": "qualified",
                    "adapter": alias,
                    "depends_on": ["session"],
                    "skills": [],
                    "requires_evidence": {"session": ["historical_pit"]},
                },
            ],
        }
        plan = build_plan(workflow, config)
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "tasks.sqlite"
            with Store(database) as store:
                wid = store.submit(plan)["workflow_id"]
                store.approve(wid, plan["plan_sha256"], ["native_session"], "integration-operator")
                result = Scheduler(store).tick(wid)
                self.assertEqual(result["steps"][0]["status"], "SUCCEEDED")
                self.assertEqual(result["steps"][1]["status"], "BLOCKED")
                self.assertIsNone(result["steps"][1]["owner_id"])
                self.assertFalse(result["research_validated"])
                self.assertFalse(result["promotion_authorized"])
                self.assertIsNone(store.metrics()["model_cost_usd"])
            with Store(database, readonly=True) as reopened:
                self.assertEqual(
                    reopened.view(wid)["steps"][0]["owner_id"],
                    config["adapters"][alias]["session_id"],
                )
