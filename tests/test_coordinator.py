import contextlib
import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.contracts import build_plan, digest, validate_workflow
from quant_task_orchestrator.scheduler import Scheduler
from quant_task_orchestrator.store import Store


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.owner_state = self.root / "owner.json"
        self.owner_state.write_text(json.dumps({"status": "SUCCEEDED", "submissions": 0}))
        self.request = self.root / "request.json"
        self.request.write_text(
            json.dumps({"idempotency_key": "synthetic-run", "budgets": {"wall_seconds": 10}})
        )
        self.config = {
            "schema": "quant.orchestrator_config.v1",
            "adapters": {
                "compute": {
                    "kind": "runtime",
                    "command": [
                        sys.executable,
                        str(Path(__file__).parent / "fixtures/owner.py"),
                        str(self.owner_state),
                    ],
                    "request": str(self.request),
                    "queue": True,
                }
            },
            "catalog": [],
        }
        self.workflow = {
            "schema": "quant.workflow.v1",
            "idempotency_key": "workflow-1",
            "title": "Synthetic study",
            "steps": [{"id": "compute", "adapter": "compute", "depends_on": [], "skills": []}],
        }
        self.store = Store(self.root / "tasks.sqlite")
        self.addCleanup(self.store.close)

    def plan(self):
        return build_plan(self.workflow, self.config)

    def submit(self, approve=True):
        plan = self.plan()
        receipt = self.store.submit(plan)
        if approve:
            self.store.approve(
                receipt["workflow_id"],
                plan["plan_sha256"],
                ["runtime", "research"],
                "test-operator",
            )
        return receipt["workflow_id"]

    def test_rejects_cycles_unknown_dependencies_and_duplicate_ids(self):
        for steps in [
            [{"id": "a", "adapter": "compute", "depends_on": ["a"], "skills": []}],
            [{"id": "a", "adapter": "compute", "depends_on": ["missing"], "skills": []}],
            [self.workflow["steps"][0], self.workflow["steps"][0]],
        ]:
            with self.subTest(steps=steps), self.assertRaises(ValueError):
                validate_workflow({**self.workflow, "steps": steps}, self.config)

    def test_idempotency_conflict_and_read_after_restart(self):
        plan = self.plan()
        first = self.store.submit(plan)
        self.assertEqual(first["workflow_id"], self.store.submit(plan)["workflow_id"])
        other = copy.deepcopy(plan)
        other["workflow"]["title"] = "Different intent"
        other["plan_sha256"] = digest({k: v for k, v in other.items() if k != "plan_sha256"})
        with self.assertRaises(ValueError):
            self.store.submit(other)
        with Store(self.root / "tasks.sqlite") as reopened:
            self.assertEqual(reopened.view(first["workflow_id"])["status"], "AWAITING_APPROVAL")

    def test_no_dispatch_without_digest_bound_permission(self):
        wid = self.submit(False)
        with self.assertRaises(ValueError):
            self.store.approve(wid, "0" * 64, ["runtime"], "operator")
        with self.assertRaises(ValueError):
            self.store.approve(wid, self.plan()["plan_sha256"], ["research"], "operator")
        Scheduler(self.store).tick(wid)
        self.assertEqual(json.loads(self.owner_state.read_text())["submissions"], 0)

    def test_runtime_verified_result_unlocks_dependency(self):
        self.workflow["steps"].append(
            {"id": "audit", "adapter": "compute", "depends_on": ["compute"], "skills": []}
        )
        wid = self.submit()
        scheduler = Scheduler(self.store)
        scheduler.tick(wid)
        scheduler.tick(wid)
        scheduler.tick(wid)
        self.assertEqual(self.store.view(wid)["status"], "SUCCEEDED")
        self.assertEqual(json.loads(self.owner_state.read_text())["submissions"], 1)
        self.assertFalse(self.store.view(wid)["promotion_authorized"])

    def test_lost_submit_response_reconciles_same_job_without_resubmit(self):
        self.owner_state.write_text(
            json.dumps({"status": "SUCCEEDED", "submissions": 0, "lose_response": True})
        )
        wid = self.submit()
        Scheduler(self.store).tick(wid)
        self.assertEqual(self.store.view(wid)["steps"][0]["status"], "UNKNOWN")
        with Store(self.root / "tasks.sqlite") as reopened:
            Scheduler(reopened).tick(wid)
            self.assertEqual(reopened.view(wid)["status"], "SUCCEEDED")
        self.assertEqual(json.loads(self.owner_state.read_text())["submissions"], 1)

    def test_crash_before_submit_is_not_blindly_retried(self):
        wid = self.submit()
        self.store.set_step(wid, "compute", "DISPATCHING")
        Scheduler(self.store).tick(wid)
        self.assertEqual(self.store.view(wid)["steps"][0]["status"], "UNKNOWN")
        self.assertEqual(json.loads(self.owner_state.read_text())["submissions"], 0)

    def test_changed_request_blocks_dispatch(self):
        wid = self.submit()
        self.request.write_text('{"idempotency_key":"changed"}')
        Scheduler(self.store).tick(wid)
        self.assertEqual(self.store.view(wid)["steps"][0]["status"], "BLOCKED")
        self.assertEqual(json.loads(self.owner_state.read_text())["submissions"], 0)

    def test_bad_result_integrity_blocks_dependents(self):
        self.owner_state.write_text(
            json.dumps({"status": "SUCCEEDED", "submissions": 0, "bad_result": True})
        )
        self.workflow["steps"].append(
            {"id": "audit", "adapter": "compute", "depends_on": ["compute"], "skills": []}
        )
        wid = self.submit()
        Scheduler(self.store).tick(wid)
        Scheduler(self.store).tick(wid)
        self.assertEqual(self.store.view(wid)["steps"][0]["status"], "UNKNOWN")
        self.assertEqual(self.store.view(wid)["steps"][1]["status"], "WAITING")

    def test_cancel_active_owner_and_stop_waiting_steps(self):
        self.owner_state.write_text(json.dumps({"status": "RUNNING", "submissions": 0}))
        self.workflow["steps"].append(
            {"id": "audit", "adapter": "compute", "depends_on": ["compute"], "skills": []}
        )
        wid = self.submit()
        Scheduler(self.store).tick(wid)
        self.store.cancel(wid)
        Scheduler(self.store).tick(wid)
        self.assertEqual(self.store.view(wid)["status"], "CANCELLED")
        self.assertEqual(json.loads(self.owner_state.read_text())["status"], "CANCELLED")

    def test_events_are_idempotent_hints_and_projection_redacts_payloads(self):
        wid = self.submit()
        event = {
            "schema": "quant.workflow_event.v1",
            "event_id": "event-1",
            "workflow_id": wid,
            "source": "runtime",
            "type": "owner.changed",
        }
        self.assertTrue(self.store.hint(event)["created"])
        self.assertFalse(self.store.hint(event)["created"])
        with self.assertRaises(ValueError):
            self.store.hint({**event, "source": "different"})
        projected = json.dumps(self.store.view(wid))
        self.assertNotIn(str(self.root), projected)
        self.assertNotIn("request.json", projected)
        self.assertEqual(self.store.view(wid)["steps"][0]["status"], "WAITING")

    def test_unknown_owner_status_and_wrong_identity_never_succeed(self):
        for extra in [{"status": "MAGIC"}, {"status": "SUCCEEDED", "wrong_identity": True}]:
            with self.subTest(extra=extra):
                self.owner_state.write_text(json.dumps({"submissions": 0, **extra}))
                self.workflow["idempotency_key"] += "-next"
                wid = self.submit()
                Scheduler(self.store).tick(wid)
                Scheduler(self.store).tick(wid)
                self.assertNotEqual(self.store.view(wid)["status"], "SUCCEEDED")

    def test_single_scheduler_fencing(self):
        wid = self.submit()
        scheduler = Scheduler(self.store)
        with scheduler.lock():
            with self.assertRaises(RuntimeError):
                Scheduler(self.store).tick(wid)

    def test_skill_content_and_version_remain_bound(self):
        source = self.root / "skills"
        source.mkdir()
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        (source / "SKILL.md").write_text("Synthetic skill\n")
        subprocess.run(["git", "-C", str(source), "add", "SKILL.md"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(source),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "fixture",
            ],
            check=True,
        )
        revision = subprocess.check_output(
            ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
        ).strip()
        self.config["catalog"] = [
            {
                "id": "audit",
                "owner_repo": "example/synthetic-owner",
                "source": str(source),
                "revision": revision,
                "path": "SKILL.md",
                "sha256": hashlib.sha256(b"Synthetic skill\n").hexdigest(),
                "permissions": ["read:evidence"],
                "input_contract": "synthetic.input.v1",
                "output_contract": "synthetic.audit.v1",
            }
        ]
        self.workflow["steps"][0]["skills"] = ["audit"]
        wid = self.submit()
        self.config["catalog"][0]["revision"] = "0" * 40
        self.assertEqual(self.store.view(wid)["skills"][0]["revision"], revision)
        with self.assertRaises(ValueError):
            self.plan()
        self.config["catalog"][0]["revision"] = revision
        self.config["catalog"][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.plan()

    def test_research_reconciles_existing_proposal_without_admission(self):
        campaign = self.root / "campaign.json"
        campaign.write_text("{}")
        self.config["adapters"]["compute"] = {
            "kind": "research",
            "command": [
                sys.executable,
                str(Path(__file__).parent / "fixtures/owner.py"),
                str(self.owner_state),
            ],
            "config": str(campaign),
            "proposal_id": "proposal-1",
        }
        wid = self.submit()
        Scheduler(self.store).tick(wid)
        Scheduler(self.store).tick(wid)
        view = self.store.view(wid)
        self.assertEqual(view["status"], "SUCCEEDED")
        self.assertFalse(view["research_validated"])
        self.assertEqual(view["steps"][0]["evidence_status"], "DIAGNOSTIC_COMPLETED")

    def test_conflicting_runtime_key_never_adopts_or_cancels_other_request(self):
        self.owner_state.write_text(
            json.dumps({"status": "RUNNING", "submissions": 1, "conflicting_request": True})
        )
        wid = self.submit()
        Scheduler(self.store).tick(wid)
        self.assertIsNone(self.store.view(wid)["steps"][0]["owner_id"])
        self.store.cancel(wid)
        Scheduler(self.store).tick(wid)
        self.assertEqual(json.loads(self.owner_state.read_text())["status"], "RUNNING")

    def test_runtime_result_must_match_approved_request_hash(self):
        self.owner_state.write_text(
            json.dumps({"status": "SUCCEEDED", "submissions": 0, "wrong_request_hash": True})
        )
        wid = self.submit()
        Scheduler(self.store).tick(wid)
        self.assertNotEqual(self.store.view(wid)["status"], "SUCCEEDED")

    def test_research_pending_proposal_is_advanced_on_subsequent_ticks(self):
        campaign = self.root / "campaign.json"
        campaign.write_text("{}")
        self.owner_state.write_text(
            json.dumps({"status": "RUNNING", "submissions": 0, "research_pending": True})
        )
        self.config["adapters"]["compute"] = {
            "kind": "research",
            "command": [
                sys.executable,
                str(Path(__file__).parent / "fixtures/owner.py"),
                str(self.owner_state),
            ],
            "config": str(campaign),
            "proposal_id": "proposal-1",
        }
        wid = self.submit()
        Scheduler(self.store).tick(wid)
        self.assertEqual(self.store.view(wid)["steps"][0]["status"], "RUNNING")
        Scheduler(self.store).tick(wid)
        self.assertEqual(self.store.view(wid)["status"], "SUCCEEDED")

    def test_cancelled_research_observes_operator_terminal_handoff(self):
        campaign = self.root / "campaign.json"
        campaign.write_text("{}")
        self.owner_state.write_text(
            json.dumps({"status": "RUNNING", "submissions": 0, "research_pending": True})
        )
        self.config["adapters"]["compute"] = {
            "kind": "research",
            "command": [
                sys.executable,
                str(Path(__file__).parent / "fixtures/owner.py"),
                str(self.owner_state),
            ],
            "config": str(campaign),
            "proposal_id": "proposal-1",
        }
        wid = self.submit()
        Scheduler(self.store).tick(wid)
        self.store.cancel(wid)
        Scheduler(self.store).tick(wid)
        self.assertEqual(self.store.view(wid)["steps"][0]["status"], "SUCCEEDED")

    def test_failed_branch_does_not_stop_other_owner_reconciliation(self):
        self.workflow["steps"].append(
            {"id": "other", "adapter": "compute", "depends_on": [], "skills": []}
        )
        wid = self.submit()
        self.store.set_step(wid, "compute", "FAILED")
        self.store.set_step(
            wid, "other", "RUNNING", owner_id="00000000-0000-4000-8000-000000000001"
        )
        self.owner_state.write_text(json.dumps({"status": "SUCCEEDED", "submissions": 1}))
        from quant_task_orchestrator.cli import main

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--database", str(self.store.path), "run", "--once"]), 0)
        self.assertEqual(self.store.view(wid)["steps"][1]["status"], "SUCCEEDED")

    def test_scheduler_sees_active_work_older_than_public_list_limit(self):
        wid = self.submit()
        plan = self.plan()
        for index in range(101):
            extra = copy.deepcopy(plan)
            extra["workflow"]["idempotency_key"] = f"newer-{index}"
            extra["plan_sha256"] = digest({k: v for k, v in extra.items() if k != "plan_sha256"})
            newer = self.store.submit(extra)["workflow_id"]
            self.store.set_step(newer, "compute", "SUCCEEDED")
        from quant_task_orchestrator.cli import main

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--database", str(self.store.path), "run", "--once"]), 0)
        self.assertEqual(self.store.view(wid)["status"], "SUCCEEDED")

    def test_cancelled_upstream_explicitly_blocks_dependents(self):
        self.workflow["steps"].append(
            {"id": "audit", "adapter": "compute", "depends_on": ["compute"], "skills": []}
        )
        wid = self.submit()
        self.store.set_step(wid, "compute", "CANCELLED")
        Scheduler(self.store).tick(wid)
        view = self.store.view(wid)
        self.assertEqual(view["status"], "BLOCKED")
        self.assertEqual(view["steps"][1]["error_code"], "DEPENDENCY_UNAVAILABLE")
        self.assertEqual(json.loads(self.owner_state.read_text())["submissions"], 0)

    def test_public_budget_projection_uses_only_declared_numeric_ceilings(self):
        self.request.write_text(
            json.dumps(
                {
                    "idempotency_key": "synthetic-run",
                    "budgets": {"wall_seconds": 10, "private_note": str(self.root)},
                }
            )
        )
        wid = self.submit()
        self.assertEqual(self.store.view(wid)["steps"][0]["budgets"], {"wall_seconds": 10})


if __name__ == "__main__":
    unittest.main()
