"""Same-origin loopback workbench and read-only query API; never invokes owners."""

import ipaddress
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .store import Store

ASSETS = {
    "/": "live.html",
    "/live.html": "live.html",
    "/live.js": "live.js",
    "/live-locales.js": "live-locales.js",
    "/live.css": "live.css",
    "/styles.css": "styles.css",
    "/favicon.svg": "favicon.svg",
}
TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}


def asset_root():
    installed = Path(__file__).parent / "web"
    return installed if installed.is_dir() else Path(__file__).resolve().parents[2] / "site"


def handler_for(database):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def allowed_request(self):
            host = self.headers.get("Host", "")
            try:
                parsed = urlsplit("//" + host)
                allowed = (
                    parsed.hostname == "localhost"
                    or ipaddress.ip_address(parsed.hostname).is_loopback
                )
            except (ValueError, TypeError):
                allowed = False
            origin = self.headers.get("Origin")
            return allowed and (origin is None or origin in {"http://" + host, "https://" + host})

        def respond(self, status, body, content_type):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status, value):
            self.respond(
                status,
                json.dumps(value, allow_nan=False).encode(),
                "application/json; charset=utf-8",
            )

        def do_GET(self):
            if not self.allowed_request():
                return self.send_json(403, {"code": "LOCAL_ORIGIN_REQUIRED"})
            url = urlsplit(self.path)
            if url.scheme or url.netloc:
                return self.send_json(400, {"code": "INVALID_QUERY"})
            if url.path in ASSETS:
                try:
                    file = asset_root() / ASSETS[url.path]
                    return self.respond(200, file.read_bytes(), TYPES[file.suffix])
                except OSError:
                    return self.send_json(503, {"code": "WORKBENCH_ASSETS_UNAVAILABLE"})
            parts = url.path.strip("/").split("/")
            query = parse_qs(url.query)
            try:
                limit = int(query.get("limit", ["100"])[0])
                offset = int(query.get("offset", ["0"])[0])
                after = int(query.get("after", ["0"])[0])
                tail = int(query["tail"][0]) if "tail" in query else None
                if (
                    not 1 <= limit <= 1000
                    or offset < 0
                    or after < 0
                    or (tail is not None and not 1 <= tail <= 500)
                ):
                    raise ValueError("INVALID_QUERY")
            except (ValueError, TypeError):
                return self.send_json(400, {"code": "INVALID_QUERY"})
            try:
                with Store(database, readonly=True) as store:
                    if parts == ["v1", "workflows"]:
                        result = {
                            "schema": "quant.workflow_list.v1",
                            "workflows": store.list(limit, offset),
                            "pagination": store.pagination(limit, offset),
                        }
                    elif parts == ["v1", "metrics"]:
                        result = store.metrics()
                    elif len(parts) == 3 and parts[:2] == ["v1", "workflows"]:
                        result = store.view(parts[2])
                    elif (
                        len(parts) == 4
                        and parts[:2] == ["v1", "workflows"]
                        and parts[3] == "events"
                    ):
                        result = {
                            "schema": "quant.workflow_events.v1",
                            "events": store.events(parts[2], after, tail=tail),
                        }
                    else:
                        return self.send_json(404, {"code": "NOT_FOUND"})
                self.send_json(200, result)
            except ValueError:
                self.send_json(404, {"code": "WORKFLOW_UNAVAILABLE"})
            except (OSError, sqlite3.Error):
                self.send_json(503, {"code": "DATABASE_UNAVAILABLE"})

        def do_POST(self):
            self.send_json(405, {"code": "READ_ONLY_API"})

        do_PUT = do_POST
        do_DELETE = do_POST
        do_PATCH = do_POST

    return Handler


def serve(database, host="127.0.0.1", port=8787):
    if not ipaddress.ip_address(host).is_loopback or ":" in host:
        raise ValueError("IPV4_LOOPBACK_REQUIRED")
    with Store(database, readonly=True):
        pass
    with HTTPServer((host, port), handler_for(database)) as server:
        server.serve_forever()
