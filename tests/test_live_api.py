"""Live assets and query routes remain local, bounded and strictly read-only."""

import http.client
import json
import threading
import unittest
from http.server import HTTPServer

import test_coordinator

from quant_task_orchestrator.api import handler_for


class LiveAPITests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.wid = self.fixture.submit()
        self.server = HTTPServer(("127.0.0.1", 0), handler_for(self.fixture.store.path))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def request(self, path, method="GET", headers=None):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        client.request(method, path, headers=headers or {})
        response = client.getresponse()
        result = response.status, response.read(), dict(response.getheaders())
        client.close()
        return result

    def test_live_page_and_assets_are_served_without_owner_effects(self):
        status, body, headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"live.js", body)
        self.assertEqual(self.request("/live.js")[0], 200)
        self.assertEqual(self.request("/../../AGENTS.md")[0], 404)
        self.assertEqual(json.loads(self.fixture.owner_state.read_text())["submissions"], 0)
        self.assertIn("Content-Security-Policy", headers)

    def test_metrics_and_paginated_queries_never_mutate_owner(self):
        status, body, _ = self.request("/v1/workflows?limit=1&offset=0")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["pagination"]["total"], 1)
        self.assertEqual(self.request("/v1/workflows?limit=0")[0], 400)
        self.assertEqual(json.loads(self.request("/v1/metrics")[1])["workflow_count"], 1)
        self.assertEqual(json.loads(self.fixture.owner_state.read_text())["submissions"], 0)

    def test_untrusted_host_origin_and_http_writes_are_rejected(self):
        self.assertEqual(self.request("/v1/workflows", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(
            self.request("/v1/workflows", headers={"Origin": "https://evil.example"})[0], 403
        )
        self.assertEqual(self.request("/v1/workflows", method="POST")[0], 405)

    def test_event_tail_returns_latest_window(self):
        for index in range(5):
            self.fixture.store.hint(
                {
                    "schema": "quant.workflow_event.v1",
                    "event_id": f"hint-{index}",
                    "workflow_id": self.wid,
                    "source": "synthetic",
                    "type": "owner.changed",
                }
            )
        status, body, _ = self.request(f"/v1/workflows/{self.wid}/events?tail=2")
        self.assertEqual(status, 200)
        events = json.loads(body)["events"]
        self.assertEqual(len(events), 2)
        self.assertEqual([e["seq"] for e in events], [6, 7])


if __name__ == "__main__":
    unittest.main()
