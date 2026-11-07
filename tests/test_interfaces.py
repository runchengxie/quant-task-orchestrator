import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import test_coordinator

from quant_task_orchestrator.api import handler_for
from quant_task_orchestrator.tui import render


class InterfaceTests(unittest.TestCase):
    def test_tui_exposes_evidence_separately_from_execution(self):
        text = render(
            [
                {
                    "workflow_id": "study",
                    "title": "Synthetic",
                    "status": "BLOCKED",
                    "steps": [
                        {
                            "id": "compute",
                            "status": "SUCCEEDED",
                            "kind": "runtime",
                            "evidence_status": "RESULT_INTEGRITY_VERIFIED",
                        }
                    ],
                }
            ]
        )
        self.assertIn("SUCCEEDED", text)
        self.assertIn("RESULT_INTEGRITY_VERIFIED", text)
        self.assertIn("BLOCKED", text)

    def test_cli_read_only_missing_database_does_not_initialize_it(self):
        with tempfile.TemporaryDirectory() as root:
            database = Path(root) / "missing.sqlite"
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "quant_task_orchestrator",
                    "--database",
                    str(database),
                    "list",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(database.exists())
            self.assertEqual(json.loads(result.stderr)["code"], "DATABASE_UNAVAILABLE")

    def test_api_rejects_writes_and_reads_projection(self):
        import http.client
        import threading
        from http.server import HTTPServer

        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            wid = fixture.submit()
            server = HTTPServer(("127.0.0.1", 0), handler_for(fixture.store.path))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = http.client.HTTPConnection("127.0.0.1", server.server_port)
                client.request("GET", "/v1/workflows/" + wid)
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                raw = response.read().decode()
                self.assertNotIn(str(fixture.root), raw)
                self.assertEqual(json.loads(raw)["workflow_id"], wid)
                client.request("POST", "/v1/workflows/" + wid)
                self.assertEqual(client.getresponse().status, 405)
                client.close()
            finally:
                server.shutdown()
                thread.join()
                server.server_close()
        finally:
            fixture.doCleanups()
