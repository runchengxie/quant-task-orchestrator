"""Coordinator adapters invoke the bounded owner, never raw model commands."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.contracts import build_plan
from quant_task_orchestrator.scheduler import Scheduler
from quant_task_orchestrator.store import Store


class CodexOwnerTests(unittest.TestCase):
    def test_start_poll_cancel_and_usage_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompt = root / "prompt.txt"
            prompt.write_text("Synthetic task")
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "schema": "research.codex-task/v1",
                        "executable": sys.executable,
                        "executable_sha256": hashlib.sha256(
                            Path(sys.executable).read_bytes()
                        ).hexdigest(),
                        "prompt_file": str(prompt),
                        "prompt_sha256": hashlib.sha256(prompt.read_bytes()).hexdigest(),
                        "work_directory": str(root / "work"),
                        "model": "synthetic",
                        "wall_seconds": 60,
                        "max_turns": 2,
                        "max_observed_tokens": 100,
                        "state_directory": str(root / "state"),
                        "output_directory": str(root / "output"),
                    }
                )
            )
            (root / "work").mkdir()
            state = root / "peer.json"
            state.write_text("{}")
            command = [
                sys.executable,
                str(Path(__file__).parent / "fixtures/codex_task_owner.py"),
                str(state),
            ]
            adapter = {
                "kind": "codex_task",
                "command": command,
                "config": str(config),
                "key": "synthetic-key",
                "action": "start",
                "session_id": None,
                "receipt": None,
            }
            cfg = {
                "schema": "quant.orchestrator_config.v1",
                "adapters": {"codex": adapter},
                "catalog": [],
            }
            workflow = {
                "schema": "quant.workflow.v1",
                "idempotency_key": "codex-flow",
                "title": "Synthetic Codex task",
                "steps": [{"id": "agent", "adapter": "codex", "depends_on": [], "skills": []}],
            }
            plan = build_plan(workflow, cfg)
            with Store(root / "workflow.sqlite") as store:
                wid = store.submit(plan)["workflow_id"]
                store.approve(wid, plan["plan_sha256"], ["codex_task"], "operator")
                view = Scheduler(store).tick(wid)
                self.assertEqual(view["steps"][0]["status"], "RUNNING")
                view = Scheduler(store).tick(wid)
                self.assertEqual(view["status"], "SUCCEEDED")
                self.assertEqual(view["steps"][0]["execution"]["observed_tokens"], 12)
                self.assertEqual(store.metrics()["observed_tokens"], 12)
                self.assertFalse(view["promotion_authorized"])
                self.assertNotIn(str(root), json.dumps(view))

    def test_cancellation_scope_is_only_codex(self):
        from quant_task_orchestrator.codex_owner import grade_codex

        binding = {"key": "task", "target_turn": 1, "owner_plan_sha256": "a" * 64}
        receipt = {
            "owner_id": "task",
            "plan_sha256": "a" * 64,
            "status": "cancel_requested",
            "turn": 1,
            "session": None,
        }
        self.assertEqual(grade_codex(binding, receipt)[:2], ("RUNNING", "task"))
