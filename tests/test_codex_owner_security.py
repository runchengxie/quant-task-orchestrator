"""Offline synthetic owner protocol, resume identity and public usage projections."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.codex_owner import (
    bind_codex,
    dispatch,
    execution_codex,
    grade_codex,
    project_execution,
)
from quant_task_orchestrator.contracts import build_plan
from quant_task_orchestrator.store import Store


class CodexProtocolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prompt = self.root / "prompt"
        self.prompt.write_text("Private synthetic prompt never projected")
        self.config = self.root / "config.json"
        self.state = self.root / "peer.json"
        self.state.write_text("{}")
        (self.root / "work").mkdir()
        config = {
            "schema": "research.codex-task/v1",
            "executable": sys.executable,
            "executable_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
            "prompt_file": str(self.prompt),
            "prompt_sha256": hashlib.sha256(self.prompt.read_bytes()).hexdigest(),
            "work_directory": str(self.root / "work"),
            "model": "synthetic",
            "wall_seconds": 60,
            "max_turns": 2,
            "max_observed_tokens": 100,
            "state_directory": str(self.root / "state"),
            "output_directory": str(self.root / "output"),
        }
        self.config.write_text(json.dumps(config))
        self.adapter = {
            "kind": "codex_task",
            "command": [
                sys.executable,
                str(Path(__file__).parent / "fixtures/codex_task_owner.py"),
                str(self.state),
            ],
            "config": str(self.config),
            "key": "synthetic-key",
            "action": "start",
            "session_id": None,
            "receipt": None,
        }

    def completed(self):
        binding = bind_codex(self.adapter)
        dispatch(binding, "start")
        return binding, dispatch(binding, "inspect")

    def test_poll_never_resumes_and_explicit_resume_is_exact(self):
        binding, receipt = self.completed()
        dispatch(binding, "inspect")
        self.assertNotIn("resume", json.loads(self.state.read_text())["_operations"])
        adapter = {
            **self.adapter,
            "action": "resume",
            "session_id": receipt["session"],
            "receipt": receipt["receipt"],
        }
        resumed = bind_codex(adapter)
        self.assertEqual(resumed["target_turn"], 2)
        pending = dispatch(resumed, "start")
        self.assertEqual(pending["turn"], 2)
        self.assertEqual(pending["session"], receipt["session"])
        done = dispatch(resumed, "inspect")
        self.assertEqual(grade_codex(resumed, done)[0], "SUCCEEDED")
        self.assertEqual(done["owner_id"], receipt["owner_id"])
        self.assertEqual(json.loads(self.state.read_text())["_operations"].count("resume"), 1)

    def test_resume_wrong_session_and_changed_prior_bytes_are_rejected(self):
        binding, receipt = self.completed()
        adapter = {
            **self.adapter,
            "action": "resume",
            "session_id": "wrong-session",
            "receipt": receipt["receipt"],
        }
        with self.assertRaisesRegex(ValueError, "PRIOR_CODEX"):
            bind_codex(adapter)
        adapter["session_id"] = receipt["session"]
        resumed = bind_codex(adapter)
        Path(receipt["receipt"]).write_text("{}")
        with self.assertRaisesRegex(ValueError, "BINDING_CHANGED"):
            dispatch(resumed, "start")

    def test_terminal_event_and_receipt_tampering_fail_closed(self):
        binding, receipt = self.completed()
        path = Path(receipt["receipt"])
        events = path.with_suffix(".events.jsonl")
        events.write_text("tampered")
        with self.assertRaisesRegex(ValueError, "EVENTS_HASH"):
            grade_codex(binding, receipt)
        events.write_text("{}\n")
        path.write_text("{}")
        with self.assertRaisesRegex(ValueError, "RECEIPT_HASH"):
            grade_codex(binding, receipt)

    def test_usage_is_nullable_nonnegative_and_never_priced(self):
        binding, receipt = self.completed()
        execution = execution_codex(binding, receipt)
        self.assertEqual(execution["observed_tokens"], 12)
        self.assertIsNone(execution["model_cost_usd"])
        self.assertNotIn(str(self.root), json.dumps(execution))
        self.assertNotIn("Private synthetic", json.dumps(execution))
        for bad in (-1, True, 1.2, "12"):
            with self.assertRaisesRegex(ValueError, "USAGE"):
                project_execution({**execution, "observed_tokens": bad})
        unknown = project_execution({**execution, "observed_tokens": None, "usage": None})
        self.assertIsNone(unknown["observed_tokens"])
        self.assertTrue(all(value is None for value in unknown["usage"].values()))
        self.assertFalse(unknown["runtime_jobs_cancelled"])

    def test_store_restart_old_readonly_and_usage_dedup(self):
        binding, receipt = self.completed()
        execution = execution_codex(binding, receipt)
        config = {
            "schema": "quant.orchestrator_config.v1",
            "adapters": {"codex": self.adapter},
            "catalog": [],
        }
        database = self.root / "workflow.sqlite"
        ids = []
        with Store(database) as store:
            for key in ("flow-one", "flow-two"):
                workflow = {
                    "schema": "quant.workflow.v1",
                    "idempotency_key": key,
                    "title": "Synthetic",
                    "steps": [{"id": "agent", "adapter": "codex", "depends_on": [], "skills": []}],
                }
                plan = build_plan(workflow, config)
                wid = store.submit(plan)["workflow_id"]
                ids.append(wid)
                store.complete_step(
                    wid,
                    "agent",
                    "SUCCEEDED",
                    "synthetic-key",
                    "CODEX_TURN_COMPLETED",
                    {},
                    execution,
                )
            self.assertEqual(store.metrics()["observed_tokens"], 12)
        with Store(database, readonly=True) as store:
            self.assertEqual(store.view(ids[0])["steps"][0]["execution"], execution)
            self.assertEqual(store.metrics()["observed_tokens"], 12)
        with Store(database) as store:
            store.db.execute("DROP TABLE execution_snapshots")
            store.db.commit()
        with Store(database, readonly=True) as store:
            self.assertIsNone(store.view(ids[0])["steps"][0]["execution"])
            self.assertEqual(store.metrics()["observed_tokens"], 0)

    def test_cancellation_is_pending_until_owner_confirms(self):
        binding = bind_codex(self.adapter)
        dispatch(binding, "start")
        pending = dispatch(binding, "cancel")
        self.assertEqual(grade_codex(binding, pending)[0], "RUNNING")
        cancelled = dispatch(binding, "inspect")
        self.assertEqual(grade_codex(binding, cancelled)[0], "CANCELLED")
        self.assertFalse(execution_codex(binding, cancelled)["runtime_jobs_cancelled"])
