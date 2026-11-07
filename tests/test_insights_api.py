"""Insights queries share bearer authorization and never execute an owner."""

import copy
import json
import unittest
from urllib.parse import urlencode

import test_private_api

from quant_task_orchestrator.analysis_reports import record_evaluation
from quant_task_orchestrator.contracts import build_plan
from quant_task_orchestrator.evaluation import reference_trace


class InsightsApiTests(unittest.TestCase):
    def setUp(self):
        self.peer = test_private_api.PrivateAPITests(
            "test_static_login_page_public_but_api_requires_bearer"
        )
        self.peer.setUp()
        self.addCleanup(self.peer.doCleanups)
        self.coordinator = self.peer.fixture
        workflow = copy.deepcopy(self.coordinator.workflow)
        workflow["idempotency_key"] = "other"
        workflow["title"] = "Other"
        self.other = self.coordinator.store.submit(build_plan(workflow, self.coordinator.config))[
            "workflow_id"
        ]
        self.headers = {"Authorization": "Bearer " + self.peer.token}

    def test_readonly_queries_and_typed_errors(self):
        path = "/v1/compare?" + urlencode({"before": self.peer.wid, "after": self.other})
        self.assertEqual(self.peer.request(path)[0], 401)
        status, body = self.peer.request(path, self.headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["schema"], "quant.workflow_comparison.v1")
        self.assertNotIn(str(self.coordinator.root), body.decode())
        self.assertEqual(self.peer.request("/v1/compare?before=a", self.headers)[0], 400)
        status, body = self.peer.request("/v1/history", self.headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["total"], 0)
        self.assertEqual(
            self.peer.request("/v1/history?classification=bad&classification=other", self.headers)[
                0
            ],
            400,
        )
        record_evaluation(self.coordinator.store, reference_trace())
        status, body = self.peer.request("/v1/evaluations", self.headers)
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["reports"][0]["model_evaluated"])
        proposal = {
            "schema": "quant.change_proposal.v1",
            "kind": "pinned_input",
            "previous": "a" * 64,
            "next": "b" * 64,
        }
        status, body = self.peer.request(
            "/v1/impact?" + urlencode({"proposal": json.dumps(proposal)}), self.headers
        )
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)["execution_authorized"])
        self.assertEqual(
            self.peer.request(
                "/v1/impact?" + urlencode({"proposal": "[" * 1500 + "]" * 1500}), self.headers
            )[0],
            400,
        )
        self.assertEqual(self.peer.request("/v1/history", self.headers, "POST")[0], 405)
        self.assertEqual(json.loads(self.coordinator.owner_state.read_text())["submissions"], 0)
