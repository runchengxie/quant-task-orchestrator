"""Live UI smoke against isolated coordinator SQLite and HTTP fixtures.

Run with Playwright and QUANT_BROWSER_EXECUTABLE set to an installed Chromium.
Real API/SQLite integration runs first; HTTP fixtures exercise outage and XSS behavior.
"""

import functools
import json
import os
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright


def fixture_smoke():
    root = Path(__file__).resolve().parents[1]
    state = {"offline": False, "empty": False, "methods": []}
    workflow = {
        "workflow_id": "workflow-1",
        "title": "<img src=x onerror=alert(1)>",
        "status": "blocked",
        "plan_sha256": "abc",
        "approved": True,
        "research_validated": False,
        "promotion_authorized": False,
        "created_at": "2026-11-07T00:00:00Z",
        "updated_at": "2026-11-07T00:01:00Z",
        "steps": [
            {"id": "data", "status": "succeeded", "owner_id": "data-owner", "depends_on": []},
            {
                "id": "review",
                "status": "blocked",
                "owner_id": "research-owner",
                "depends_on": ["data"],
                "evidence": {
                    "checks": {"input_integrity": {"status": "verified", "source": "data-owner"}}
                },
                "recovery": {
                    "code": "pit_missing",
                    "actions": ["collect_pit_evidence"],
                    "requires_operator": True,
                },
            },
        ],
    }

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            if not url.path.startswith("/v1/"):
                if url.path == "/":
                    self.path = "/live.html"
                return super().do_GET()
            state["methods"].append(self.command)
            if state["offline"]:
                self.send_error(503)
                return
            if url.path == "/v1/workflows":
                offset = int(parse_qs(url.query).get("offset", [0])[0])
                items = (
                    []
                    if state["empty"]
                    else [
                        dict(workflow, workflow_id=f"workflow-{i + 1}")
                        for i in range(offset, min(offset + 100, 101))
                    ]
                )
                payload = {
                    "schema": "quant.workflow_list.v1",
                    "workflows": items,
                    "pagination": {"total": 0 if state["empty"] else 101, "has_more": not offset},
                }
            elif url.path == "/v1/metrics":
                payload = {
                    "schema": "quant.orchestrator_metrics.v1",
                    "workflow_count": 2,
                    "step_count": 4,
                    "owner_calls": 1,
                    "owner_errors": 0,
                    "model_cost_usd": None,
                }
            elif url.path.endswith("/events"):
                payload = {
                    "events": [
                        {
                            "seq": 1,
                            "type": "step_blocked",
                            "step_id": "review",
                            "created": "2026-11-07T00:01:00Z",
                        }
                    ]
                }
            else:
                payload = dict(workflow, workflow_id=url.path.rsplit("/", 1)[-1])
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Handler, directory=str(root / "site"))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, executable_path=os.environ.get("QUANT_BROWSER_EXECUTABLE")
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            expect(page.locator(".live-workflow")).to_have_count(100)
            expect(page.locator("#health")).to_contain_text("Connected")
            assert page.locator("#detail img").count() == 0
            assert page.locator(".live-layer").count() == 2
            page.locator(".live-step").nth(1).click()
            expect(page.locator("#detail")).to_contain_text(
                "Collect historical point-in-time evidence"
            )
            expect(page.locator(".live-check")).to_have_count(6)
            page.locator("#more").click()
            expect(page.locator(".live-workflow")).to_have_count(101)
            page.locator("#status").select_option("blocked")
            expect(page.locator(".live-workflow")).to_have_count(101)
            page.locator("#status").select_option("")
            expect(page.locator(".live-workflow")).to_have_count(101)
            page.locator("#search").fill("not-found")
            expect(page.locator(".live-workflow")).to_have_count(0)
            page.locator("#search").fill("")
            page.locator("#language").select_option("zh-CN")
            page.reload()
            expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
            page.locator("#language").select_option("en")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator("#refresh").focus()
            assert page.evaluate("document.activeElement.id") == "refresh"
            state["offline"] = True
            page.locator("#refresh").click()
            expect(page.locator("#health")).to_contain_text("Live API unavailable")
            expect(page.locator("#setup")).to_be_visible()
            state["offline"], state["empty"] = False, True
            page.locator("#refresh").click()
            expect(page.locator("#health")).to_contain_text("Connected")
            expect(page.locator("#workflows")).to_contain_text("No workflows")
            assert set(state["methods"]) == {"GET"}
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    print("Live browser fixture smoke passed")


def real_database_smoke():
    """Serve the production API against a new temporary coordinator SQLite DB."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from quant_task_orchestrator.api import handler_for
    from quant_task_orchestrator.contracts import build_plan
    from quant_task_orchestrator.store import Store

    with tempfile.TemporaryDirectory(prefix="quant-live-smoke-") as temporary:
        root = Path(temporary)
        request = root / "request.json"
        request.write_text(
            json.dumps({"idempotency_key": "browser-smoke", "budgets": {"wall_seconds": 10}})
        )
        owner_state = root / "owner-state.json"
        owner_state.write_text(json.dumps({"status": "SUCCEEDED", "submissions": 0}))
        config = {
            "schema": "quant.orchestrator_config.v1",
            "adapters": {
                "compute": {
                    "kind": "runtime",
                    "command": [
                        sys.executable,
                        str(Path(__file__).parent / "fixtures" / "owner.py"),
                        str(owner_state),
                    ],
                    "request": str(request),
                    "queue": True,
                }
            },
            "catalog": [],
        }
        workflow = {
            "schema": "quant.workflow.v1",
            "idempotency_key": "browser-workflow",
            "title": "Retained browser acceptance",
            "steps": [
                {"id": "compute", "adapter": "compute", "depends_on": [], "skills": []},
                {"id": "review", "adapter": "compute", "depends_on": ["compute"], "skills": []},
            ],
        }
        database = root / "coordinator.sqlite"
        with Store(database) as store:
            receipt = store.submit(build_plan(workflow, config))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(database))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(
                    headless=True, executable_path=os.environ.get("QUANT_BROWSER_EXECUTABLE")
                )
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/")
                expect(page.locator("#health")).to_contain_text("Connected")
                expect(page.locator(".live-workflow")).to_have_count(1)
                expect(page.locator("#detail")).to_contain_text("Retained browser acceptance")
                expect(page.locator(".live-layer")).to_have_count(2)
                expect(page.locator(".live-check")).to_have_count(6)
                page.locator("#status").select_option("AWAITING_APPROVAL")
                expect(page.locator(".live-workflow")).to_have_count(1)
                page.locator("#status").select_option("")
                expect(page.locator(".live-workflow")).to_have_count(1)
                # Change retained coordinator state; refresh must read it from SQLite.
                with Store(database) as store:
                    store.set_step(
                        receipt["workflow_id"], "compute", "BLOCKED", error="OWNER_UNAVAILABLE"
                    )
                expect(page.locator("#detail")).to_contain_text("OWNER_UNAVAILABLE", timeout=10000)
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    print("Live browser coordinator SQLite smoke passed")


if __name__ == "__main__":
    real_database_smoke()
    fixture_smoke()
