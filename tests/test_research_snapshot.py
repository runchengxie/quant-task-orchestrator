"""Research tool snapshots prove content identity without asserting research trust."""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.contracts import build_plan
from quant_task_orchestrator.owners import Owner
from quant_task_orchestrator.research_snapshot import validate
from quant_task_orchestrator.scheduler import Scheduler
from quant_task_orchestrator.store import Store


class ResearchSnapshotTests(unittest.TestCase):
    def test_wrong_receipt_identity_fails_closed(self):
        binding = {
            "expected_profile_sha256": "a" * 64,
            "handle": "sample",
            "resource_kind": "evidence",
            "content_sha256": "b" * 64,
        }
        receipt = {
            "schema": "research.tool-response/v1",
            "profile_sha256": "a" * 64,
            "handle": "sample",
            "kind": "evidence",
            "content_sha256": "b" * 64,
            "snapshot": True,
        }
        validate(binding, receipt)
        for field in receipt:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(binding, {**receipt, field: False})

    def test_snapshot_is_readonly_and_does_not_trust_embedded_pit_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            content = root / "evidence.json"
            content.write_text(
                json.dumps({"historical_pit": "verified", "private_path": str(root)})
            )
            content_sha = hashlib.sha256(content.read_bytes()).hexdigest()
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "schema": "research.tool-profile/v1",
                        "root": str(root),
                        "resources": {
                            "sample": {
                                "kind": "evidence",
                                "path": "evidence.json",
                                "sha256": content_sha,
                                "max_bytes": 4096,
                            }
                        },
                    }
                )
            )
            profile_sha = hashlib.sha256(profile.read_bytes()).hexdigest()
            peer = root / "peer.py"
            peer.write_text(
                "import json,sys\nprint("
                + repr(
                    json.dumps(
                        {
                            "schema": "research.tool-response/v1",
                            "profile_sha256": profile_sha,
                            "handle": "sample",
                            "kind": "evidence",
                            "content_sha256": content_sha,
                            "snapshot": True,
                            "content": json.loads(content.read_text()),
                        }
                    )
                )
                + ")\n"
            )
            config = {
                "schema": "quant.orchestrator_config.v1",
                "adapters": {
                    "evidence": {
                        "kind": "research_snapshot",
                        "command": [sys.executable, str(peer)],
                        "profile": str(profile),
                        "expected_profile_sha256": profile_sha,
                        "handle": "sample",
                    }
                },
                "catalog": [],
            }
            workflow = {
                "schema": "quant.workflow.v1",
                "idempotency_key": "snapshot",
                "title": "Synthetic snapshot acceptance",
                "steps": [
                    {"id": "evidence", "adapter": "evidence", "depends_on": [], "skills": []},
                    {
                        "id": "qualified",
                        "adapter": "evidence",
                        "depends_on": ["evidence"],
                        "skills": [],
                        "requires_evidence": {"evidence": ["historical_pit"]},
                    },
                ],
            }
            plan = build_plan(workflow, config)
            with Store(root / "state.sqlite") as store:
                wid = store.submit(plan)["workflow_id"]
                store.approve(wid, plan["plan_sha256"], ["research_snapshot"], "acceptance")
                view = Scheduler(store).tick(wid)
                self.assertEqual(view["steps"][0]["status"], "SUCCEEDED")
                self.assertEqual(
                    view["steps"][0]["evidence"]["checks"]["historical_pit"]["status"], "unknown"
                )
                self.assertEqual(view["steps"][1]["status"], "BLOCKED")
                self.assertNotIn(str(root), json.dumps(view))
                self.assertFalse(view["promotion_authorized"])
            profile.write_text("{}")
            with self.assertRaisesRegex(ValueError, "BINDING_CHANGED"):
                Owner(plan["adapters"]["evidence"]).start()
