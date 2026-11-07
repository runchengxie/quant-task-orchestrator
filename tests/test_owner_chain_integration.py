"""Installed owner protocol chain; synthetic inputs do not qualify economic research."""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from quant_task_orchestrator.contracts import build_plan
from quant_task_orchestrator.scheduler import Scheduler
from quant_task_orchestrator.store import Store

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
from asset_owner import data_fixture, report_fixture


@unittest.skipUnless(
    all(
        os.environ.get(name)
        for name in (
            "QUANT_RUNTIME_CLI",
            "QUANT_RUNTIME_PYTHON",
            "QUANT_RUNTIME_EXAMPLE",
            "QUANT_DATA_OWNER_CLI",
            "QUANT_REPORT_OWNER_CLI",
        )
    ),
    "explicit installed owners required",
)
class InstalledChainTests(unittest.TestCase):
    def test_data_compute_report_chain_recovers_but_qualification_stays_blocked(self):
        with tempfile.TemporaryDirectory(prefix="quant-chain-") as temporary:
            root = Path(temporary)
            data_dir = root / "data"
            data_dir.mkdir()
            report_dir = root / "report"
            report_dir.mkdir()
            compute = root / "compute"
            compute.mkdir()
            data, _ = data_fixture(data_dir)
            data["command"] = [os.environ["QUANT_DATA_OWNER_CLI"]]
            report, _ = report_fixture(report_dir)
            report["command"] = [os.environ["QUANT_REPORT_OWNER_CLI"]]
            subprocess.run(
                [
                    os.environ["QUANT_RUNTIME_PYTHON"],
                    os.environ["QUANT_RUNTIME_EXAMPLE"],
                    "--output",
                    str(compute),
                ],
                capture_output=True,
                check=True,
            )
            command = [
                os.environ["QUANT_RUNTIME_CLI"],
                "--database",
                str(compute / "jobs.sqlite"),
                "--artifact-root",
                str(compute / "artifacts"),
                "--result-root",
                str(compute / "results"),
                "--error-format",
                "json",
            ]
            if os.environ.get("QUANT_RUNTIME_ADAPTER_PYTHON"):
                command += ["--python-executable", os.environ["QUANT_RUNTIME_ADAPTER_PYTHON"]]
            subprocess.run([*command, "recover"], check=True, capture_output=True)
            runtime = {
                "kind": "runtime",
                "command": command,
                "request": str(compute / "request.json"),
                "queue": False,
            }
            config = {
                "schema": "quant.orchestrator_config.v1",
                "adapters": {"data": data, "compute": runtime, "report": report},
                "catalog": [],
            }
            workflow = {
                "schema": "quant.workflow.v1",
                "idempotency_key": "installed-protocol-chain",
                "title": "Synthetic owner protocol acceptance",
                "steps": [
                    {"id": "data", "adapter": "data", "depends_on": [], "skills": []},
                    {"id": "compute", "adapter": "compute", "depends_on": ["data"], "skills": []},
                    {"id": "report", "adapter": "report", "depends_on": ["compute"], "skills": []},
                    {
                        "id": "qualified_research",
                        "adapter": "report",
                        "depends_on": ["data", "compute", "report"],
                        "skills": [],
                        "requires_evidence": {
                            "data": ["historical_pit"],
                            "compute": ["independent_review", "execution_semantics"],
                        },
                    },
                ],
            }
            plan = build_plan(workflow, config)
            database = root / "workflow.sqlite"
            with Store(database) as store:
                wid = store.submit(plan)["workflow_id"]
                store.approve(
                    wid, plan["plan_sha256"], ["data", "runtime", "report"], "acceptance-operator"
                )
                Scheduler(store).tick(wid)
            # Reopen the coordinator while the Runtime owns its independent task.
            with Store(database) as store:
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    view = Scheduler(store).tick(wid)
                    if view["steps"][2]["status"] == "SUCCEEDED":
                        break
                    time.sleep(0.2)
                self.assertEqual(
                    [step["status"] for step in view["steps"]],
                    ["SUCCEEDED", "SUCCEEDED", "SUCCEEDED", "BLOCKED"],
                    json.dumps(view),
                )
                self.assertFalse(view["research_validated"])
                self.assertFalse(view["promotion_authorized"])
                self.assertEqual(store.submit(plan)["workflow_id"], wid)
                self.assertNotIn(str(root), json.dumps(view))


@unittest.skipUnless(
    os.environ.get("QUANT_DATA_OWNER_CLI"), "explicit installed data owner required"
)
class InstalledShadowTests(unittest.TestCase):
    def test_repeated_data_shadow_preserves_inputs_and_uses_new_namespaces(self):
        import hashlib

        from quant_task_orchestrator.shadow import run_shadow

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            inputs = root / "inputs"
            inputs.mkdir()
            adapter, _ = data_fixture(inputs)
            adapter["command"] = [os.environ["QUANT_DATA_OWNER_CLI"]]
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    {
                        "schema": "quant.orchestrator_config.v1",
                        "adapters": {"data": adapter},
                        "catalog": [],
                    }
                )
            )
            sha = hashlib.sha256(config.read_bytes()).hexdigest()
            before = {
                str(p.relative_to(inputs)): p.read_bytes() for p in inputs.rglob("*") if p.is_file()
            }
            first = run_shadow(config, sha, root / "outputs")
            second = run_shadow(config, sha, root / "outputs")
            self.assertNotEqual(first["run_id"], second["run_id"])
            self.assertEqual(first["status"], "SUCCEEDED")
            self.assertEqual(first["new_model_calls"], 0)
            self.assertFalse(first["qualified_research_ready"])
            self.assertFalse(first["production_schedule_changed"])
            self.assertEqual(
                before,
                {
                    str(p.relative_to(inputs)): p.read_bytes()
                    for p in inputs.rglob("*")
                    if p.is_file()
                },
            )
