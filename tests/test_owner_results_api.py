"""Imported result queries and recorded rechecks stay authenticated and read-only."""

import hashlib
import json
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

import test_private_api
from test_economic_results import receipt

from quant_task_orchestrator.economic_cache import import_result


class OwnerResultsApiTests(unittest.TestCase):
    def setUp(self):
        self.peer = test_private_api.PrivateAPITests(
            "test_static_login_page_public_but_api_requires_bearer"
        )
        self.peer.setUp()
        self.addCleanup(self.peer.doCleanups)
        self.headers = {"Authorization": "Bearer " + self.peer.token}

    def test_cached_pair_api_and_recheck_never_call_owner(self):
        f = self.peer.fixture
        path = f.root / "result.json"
        path.write_text(json.dumps(receipt()))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        import_result(f.store, path, sha)
        path.unlink()
        self.assertEqual(self.peer.request("/v1/economic-results")[0], 401)
        with patch(
            "quant_task_orchestrator.owners.Owner.call", side_effect=AssertionError("owner called")
        ):
            status, body = self.peer.request("/v1/economic-results", self.headers)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["total"], 1)
            status, body = self.peer.request(
                "/v1/economic-compare?" + urlencode({"before": sha, "after": sha}), self.headers
            )
            self.assertEqual(status, 200)
            self.assertFalse(json.loads(body)["research_validated"])
            status, body = self.peer.request(
                "/v1/workflows/" + self.peer.wid + "/recheck", self.headers
            )
            self.assertEqual(status, 200)
            self.assertFalse(json.loads(body)["owner_refresh_performed"])
        for query in [
            "/v1/economic-results?limit=101",
            "/v1/economic-results?limit=1&limit=2",
            "/v1/economic-compare?before=bad&after=bad",
            "/v1/economic-compare?before=" + sha + "&after=" + sha + "&extra=1",
        ]:
            self.assertEqual(self.peer.request(query, self.headers)[0], 400)
        self.assertEqual(self.peer.request("/v1/economic-results", self.headers, "POST")[0], 405)
        self.assertEqual(json.loads(f.owner_state.read_text())["submissions"], 0)
