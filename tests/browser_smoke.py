"""Run with an explicitly installed Playwright; screenshots stay outside source."""

import functools
import os
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright


def main():
    root = Path(__file__).resolve().parents[1]

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=str(root / "site"))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                headless=True, executable_path=os.environ.get("QUANT_BROWSER_EXECUTABLE")
            )
            page = browser.new_page(viewport={"width": 1440, "height": 1120}, device_scale_factor=1)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(f"http://127.0.0.1:{server.server_port}", wait_until="networkidle")
            assert page.locator(".workflow-row").count() == 3
            assert (
                page.locator("#step-detail")
                .inner_text()
                .find("Historical availability is unverified")
                >= 0
            )
            page.locator('[data-workflow="synthetic-plan-03"]').click()
            page.locator("#step-action").click()
            assert "Running" in page.locator('[data-workflow="synthetic-plan-03"]').inner_text()
            page.locator("#step-action").click()
            assert (
                "Awaiting review"
                in page.locator('[data-workflow="synthetic-plan-03"]').inner_text()
            )
            page.locator("#language").click()
            assert page.locator("html").get_attribute("lang") == "zh-CN"
            page.reload(wait_until="networkidle")
            assert page.locator("html").get_attribute("lang") == "zh-CN"
            page.locator("#language").click()
            page.locator('[data-filter="attention"]').click()
            assert page.locator(".workflow-row").count() == 2
            page.locator("#search").fill("no-match")
            assert page.locator(".workflow-row").count() == 0
            page.locator("#replay").click()
            assert page.locator(".workflow-row").count() == 3
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path="/tmp/quant-task-orchestrator-desktop.png", full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.locator('[data-workflow="synthetic-cost-02"]').click()
            page.locator("#step-action").click()
            assert (
                "Awaiting review"
                in page.locator('[data-workflow="synthetic-cost-02"]').inner_text()
            )
            page.screenshot(path="/tmp/quant-task-orchestrator-mobile.png", full_page=True)
            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
    print(
        "Browser acceptance passed: desktop/mobile, filters, simulation, locale persistence, no page errors."
    )


if __name__ == "__main__":
    main()
