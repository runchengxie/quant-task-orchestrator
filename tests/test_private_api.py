"""Private read-only API never exposes token values or authorizes mutations."""

import http.client
import json
import threading
import unittest
from http.server import HTTPServer

import test_coordinator

from quant_task_orchestrator.api import handler_for
from quant_task_orchestrator.auth import read_token


class PrivateAPITests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.wid = self.fixture.submit()
        self.token = "a" * 64
        self.server = HTTPServer(
            ("127.0.0.1", 0), handler_for(self.fixture.store.path, token=self.token)
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def request(self, path, headers=None, method="GET"):
        client = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        client.request(method, path, headers=headers or {})
        response = client.getresponse()
        body = response.read()
        status = response.status
        client.close()
        return status, body

    def test_static_login_page_public_but_api_requires_bearer(self):
        self.assertEqual(self.request("/")[0], 200)
        status, body = self.request("/v1/workflows")
        self.assertEqual(status, 401)
        self.assertNotIn(self.token, body.decode())
        self.assertEqual(self.request("/v1/workflows", {"Authorization": "Bearer wrong"})[0], 401)
        status, body = self.request("/v1/workflows", {"Authorization": "Bearer " + self.token})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["workflows"][0]["workflow_id"], self.wid)

    def test_auth_cannot_enable_http_writes_or_cross_origin(self):
        headers = {"Authorization": "Bearer " + self.token}
        self.assertEqual(self.request("/v1/workflows", headers, "POST")[0], 405)
        self.assertEqual(
            self.request("/v1/workflows", {**headers, "Origin": "https://evil.example"})[0], 403
        )
        self.assertEqual(self.request("/v1/workflows?token=" + self.token)[0], 401)

    def test_token_file_requires_private_permissions_and_regular_file(self):
        path = self.fixture.root / "api.token"
        path.write_text(self.token + "\n")
        path.chmod(0o600)
        self.assertEqual(read_token(path), self.token)
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            read_token(path)
        path.chmod(0o600)
        link = self.fixture.root / "token-link"
        link.symlink_to(path)
        with self.assertRaises(ValueError):
            read_token(link)


if __name__ == "__main__":
    unittest.main()
