"""Read-only insight UI, localization, escaping, and late-response logout checks."""

import functools
import json
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]
    marker = '<img src=x onerror="window.xss=true">'
    state = {
        "delay": None,
        "entered": threading.Event(),
        "release": threading.Event(),
        "requests": [],
    }
    workflow = {
        "workflow_id": "workflow-1",
        "title": "Synthetic workflow",
        "status": "BLOCKED",
        "steps": [
            {
                "id": "compute",
                "status": "SUCCEEDED",
                "depends_on": [],
                "evidence": {
                    "checks": {
                        "historical_pit": {
                            "status": "verified",
                            "source": "quant-research",
                            "evidence_sha256": "a" * 64,
                            "applicability": {"usable": False, "code": "EXPIRED"},
                            "scope": {
                                "as_of": "2025-01-01T00:00:00Z",
                                "sample_start": "2024-01-01",
                                "sample_end": "2024-12-31",
                                "data_sha256": "b" * 64,
                                "strategy_sha256": "c" * 64,
                                "universe_sha256": "d" * 64,
                            },
                            "assessed_at": "2026-01-01T00:00:00Z",
                            "valid_until": "2026-02-01T00:00:00Z",
                        }
                    }
                },
            }
        ],
    }
    payloads = {
        "/v1/compare": {
            "schema": "quant.workflow_comparison.v1",
            "steps": [
                {
                    "id": marker,
                    "status": "changed",
                    "changed_fields": ["owner_revision"],
                    "before": {"owner_revision": "a" * 40},
                    "after": {"owner_revision": "b" * 40},
                }
            ],
        },
        "/v1/history": {
            "schema": "quant.research_history.v1",
            "snapshot_sha256": "f" * 64,
            "total": 2,
            "next_offset": 50,
            "records": [
                {
                    "record_id": marker,
                    "classification": "operational_failure",
                    "status": "BLOCKED",
                    "evidence_stage": "not_verified",
                    "topic_tags": [marker],
                    "revisit_conditions": ["new-evidence"],
                }
            ],
        },
        "/v1/impact": {
            "schema": "quant.change_impact.v1",
            "scan": {
                "scope": "all_stored_workflows",
                "workflows_scanned": 2,
                "consistency": "sqlite_read_snapshot",
            },
            "affected_workflows": [
                {
                    "workflow_id": marker,
                    "direct_steps": ["compute"],
                    "downstream_steps": ["qualification"],
                }
            ],
        },
        "/v1/evaluations": {
            "schema": "quant.evaluation_list.v1",
            "reports": [
                {
                    "evaluation_scope": "reference-not-model",
                    "model_evaluated": False,
                    "passed": 7,
                    "total": 7,
                    "suite_version": "1.0.0",
                    "suite_sha256": "a" * 64,
                    "trace_sha256": "b" * 64,
                    "observed_tokens": None,
                    "cases": [{"id": marker, "passed": True, "missing_evidence": []}],
                }
            ],
        },
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
            state["requests"].append(
                (self.command, url.path, parse_qs(url.query), self.headers.get("Authorization"))
            )
            if self.headers.get("Authorization") != "Bearer fixture-token":
                self.send_error(401)
                return
            if state["delay"] == url.path:
                state["entered"].set()
                state["release"].wait(5)
            if url.path == "/v1/workflows":
                payload = {
                    "schema": "quant.workflow_list.v1",
                    "workflows": [workflow],
                    "pagination": {"total": 1},
                }
            elif url.path == "/v1/metrics":
                payload = {"schema": "quant.orchestrator_metrics.v1", "workflow_count": 1}
            elif url.path.endswith("/events"):
                payload = {"events": []}
            elif url.path in payloads:
                payload = payloads[url.path]
                if url.path == "/v1/history" and parse_qs(url.query).get("offset") == ["50"]:
                    payload = dict(payload, next_offset=None)
            else:
                payload = workflow
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

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
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}/")
            expect(page.locator("#login")).to_be_visible()

            def connect():
                page.locator("#token").fill("fixture-token")
                page.locator("#connect").click()
                expect(page.locator(".live-workflow")).to_have_count(1)
                page.locator("#insights > summary").click()

            connect()
            expired = page.locator(".live-check").nth(1)
            expect(expired).to_contain_text("Expired")
            expect(expired.locator(".live-badge.good")).to_have_count(0)
            expect(expired).to_contain_text("Market as-of")
            expect(expired).to_contain_text("Evidence assessed")
            page.locator("#compare-before").fill("workflow-1")
            page.locator("#compare-after").fill("workflow-2")
            page.locator("#compare-load").click()
            expect(page.locator("#compare-result")).to_contain_text("Changed steps: 1")
            expect(page.locator("#compare-result")).to_contain_text(
                "Economic comparison unavailable"
            )
            page.locator("#history-load").click()
            expect(page.locator("#history-result")).to_contain_text("Operational failure")
            page.locator("#history-next").click()
            expect(page.locator("#history-next")).to_be_hidden()
            page.locator("#impact-previous").fill("a" * 40)
            page.locator("#impact-next").fill("b" * 40)
            page.locator("#impact-load").click()
            expect(page.locator("#impact-result")).to_contain_text("qualification")
            expect(page.locator("#impact-result")).to_contain_text("No change was executed")
            page.locator("#evaluation-load").click()
            expect(page.locator("#evaluation-result")).to_contain_text("not model reliability")
            expect(page.locator("#evaluation-result")).to_contain_text("Provenance unverified")
            expect(page.locator("#insights img")).to_have_count(0)
            assert page.evaluate("window.xss !== true")
            page.locator("#language").select_option("zh-CN")
            expect(page.locator("#compare-result")).to_contain_text("发生变化的步骤")
            expect(page.locator("#evaluation-result")).to_contain_text("来源未经核验")
            expect(expired).to_contain_text("已过期")
            page.locator("#language").select_option("en")
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.set_viewport_size({"width": 1440, "height": 1000})
            for name, path in [
                ("compare", "/v1/compare"),
                ("history", "/v1/history"),
                ("impact", "/v1/impact"),
                ("evaluation", "/v1/evaluations"),
            ]:
                state["entered"].clear()
                state["release"].clear()
                state["delay"] = path
                page.locator(f"#{name}-load").click()
                assert state["entered"].wait(3)
                page.locator("#disconnect").click()
                state["release"].set()
                page.wait_for_timeout(200)
                for result in ("compare", "history", "impact", "evaluation"):
                    expect(page.locator(f"#{result}-result")).to_be_empty()
                expect(page.locator("#compare-before")).to_have_value("")
                state["delay"] = None
                connect()
            assert all(method == "GET" for method, *_ in state["requests"])
            assert all(
                auth == "Bearer fixture-token"
                for _, path, _, auth in state["requests"]
                if path in payloads
            )
            assert any(
                query.get("snapshot_sha256") == ["f" * 64]
                for _, path, query, _ in state["requests"]
                if path == "/v1/history"
            )
            assert not errors, errors
            assert page.evaluate("localStorage.getItem('fixture-token')") is None
            browser.close()
    finally:
        state["release"].set()
        server.shutdown()
        server.server_close()
    print(
        "Insight browser smoke passed: views, locale, escaping, GET-only auth, and four logout races"
    )


if __name__ == "__main__":
    main()
