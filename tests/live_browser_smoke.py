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
                "kind": "research",
                "status": "blocked",
                "owner_id": "research-owner",
                "depends_on": ["data"],
                "evidence": {
                    "checks": {"input_integrity": {"status": "verified", "source": "data-owner"}, "historical_pit": {"status": "missing"}, "independent_review": {"status": "not_applicable"}}
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
                        },
                        {"seq": 2, "type": "future.event_code", "step_id": "review", "created": "2026-11-07T00:02:00Z"}
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
            expect(page.locator("#overview")).to_contain_text("Loaded workflows")
            expect(page.locator("#overview [data-group=attention] strong")).to_have_text("100")
            page.locator("#overview [data-group=running]").click()
            expect(page.locator(".live-workflow")).to_have_count(0)
            page.locator("#overview [data-group=attention]").click()
            expect(page.locator(".live-workflow")).to_have_count(100)
            page.locator("#overview [data-group=attention]").click()
            assert not page.locator("#operating-metrics").evaluate("e => e.open")
            assert not page.locator("#workflow-technical").evaluate("e => e.open")
            expect(page.locator(".live-outcome")).to_contain_text("Research qualification")
            page.locator("#workflow-technical > summary").click()
            page.locator("#refresh").click()
            expect(page.locator("#workflow-technical")).to_have_attribute("open", "")
            assert page.locator("#detail img").count() == 0
            assert page.locator(".live-layer").count() == 2
            expect(page.locator(".live-next-action")).to_contain_text("Responsible system: Research")
            expect(page.locator(".live-next-action")).to_contain_text("Recorded missing evidence: Historical point-in-time")
            expect(page.locator(".live-next-action")).to_contain_text("Recorded evidence not applicable: Independent review")
            # Do not infer absent dimensions to be missing.
            assert "Economic conclusion" not in page.locator(".live-next-action").inner_text()
            page.locator(".live-step").nth(0).click()
            page.locator("#inspect-next-step").click()
            expect(page.locator(".live-step").nth(1)).to_have_attribute("aria-pressed", "true")
            assert page.evaluate("document.activeElement.id") == "step-evidence"
            page.wait_for_function("document.getElementById('step-evidence').getBoundingClientRect().top >= 0 && document.getElementById('step-evidence').getBoundingClientRect().top < 50")
            page.locator("#event-history > summary").click()
            expect(page.locator(".live-events")).to_contain_text("Step is blocked")
            expect(page.locator(".live-events")).to_contain_text("Recorded workflow event")
            unknown_event = page.locator(".live-events li").first
            assert "future.event_code" not in unknown_event.inner_text()
            unknown_event.locator("summary").click()
            expect(unknown_event).to_contain_text("future.event_code")
            expect(page.locator("#detail")).to_contain_text(
                "Collect historical point-in-time evidence"
            )
            expect(page.locator(".live-check")).to_have_count(6)
            # Every registered kind identifies its owning system, not its execution ID.
            for kind, label in [
                ("raw_observation", "Market Data"), ("data", "Market Data"),
                ("codex_task", "Research"), ("native_session", "Research"),
                ("research_snapshot", "Research"), ("runtime", "Backtest Runtime"),
                ("report", "Reports"), ("future_adapter", "Unknown"),
            ]:
                workflow["steps"][1]["kind"] = kind
                page.locator("#refresh").click()
                expect(page.locator(".live-next-action")).to_contain_text(f"Responsible system: {label}")
                assert "research-owner" not in page.locator(".live-next-action").inner_text()
            workflow["steps"][1]["kind"] = "research"
            # Approval blockers have WAITING steps; guidance must still be prominent.
            workflow["steps"][1]["status"] = "waiting"
            workflow["steps"][1]["recovery"] = {
                "code": "approval_required", "actions": ["approve_exact_plan"],
                "requires_operator": True,
            }
            page.locator("#refresh").click()
            expect(page.locator(".live-next-action")).to_contain_text("approval_required")
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
            expect(page.locator("#event-history > summary")).to_have_text("流程时间线")
            expect(page.locator("#inspect-next-step")).to_have_text("查看步骤证据与恢复建议")
            expect(page.locator(".live-next-action")).to_contain_text("负责系统: Research 研究系统")
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


def real_database_smoke(private=False):
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
        token = "browser-acceptance-" + "x" * 48 if private else None
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(database, token=token))
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
                if private:
                    expect(page.locator("#login")).to_be_visible()
                    page.locator("#token").fill(token)
                    page.locator("#connect").click()
                    expect(page.locator("#token")).to_have_value("")
                    assert page.evaluate("JSON.stringify(localStorage)") == "{}"
                    assert page.evaluate("JSON.stringify(sessionStorage)") == "{}"
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
                if private:
                    delayed = []

                    def delay_authenticated(route):
                        if route.request.headers.get("authorization"):
                            delayed.append((route, route.fetch()))
                        else:
                            route.continue_()

                    page.route("**/v1/workflows?*", delay_authenticated)
                    page.locator("#refresh").click()
                    expect(page.locator("#refresh")).to_be_disabled()
                    for _ in range(50):
                        if delayed:
                            break
                        page.wait_for_timeout(100)
                    assert delayed
                    page.locator("#disconnect").click()
                    for route, response in delayed:
                        route.fulfill(response=response)
                    page.wait_for_timeout(200)
                    expect(page.locator("#login")).to_be_visible()
                    expect(page.locator(".live-workflow")).to_have_count(0)
                    page.reload()
                    expect(page.locator("#login")).to_be_visible()
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown()
            server.server_close()
    print("Live browser coordinator SQLite smoke passed")


if __name__ == "__main__":
    real_database_smoke()
    real_database_smoke(private=True)
    fixture_smoke()
