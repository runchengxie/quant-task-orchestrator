"""Same-origin loopback workbench and read-only query API; never invokes owners."""

import ipaddress
import json
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .auth import authorized, read_token
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


def handler_for(database, *, token=None):
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
            if not authorized(self.headers.get("Authorization"), token):
                return self.send_json(401, {"code": "AUTHENTICATION_REQUIRED"})
            parts = url.path.strip("/").split("/")
            query = parse_qs(url.query)
            try:
                limit = int(query.get("limit", ["100"])[0])
                offset = int(query.get("offset", ["0"])[0])
                after = (
                    int(query.get("after", ["0"])[0])
                    if parts not in (["v1", "compare"], ["v1", "economic-compare"])
                    else 0
                )
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
                    if parts == ["v1", "health"]:
                        result = {
                            "schema": "quant.workbench_health.v1",
                            "status": "ok",
                            "mode": "read_only",
                            "authentication_required": token is not None,
                        }
                    elif parts == ["v1", "compare"]:
                        from .insights import compare_workflows

                        if set(query) != {"before", "after"} or any(
                            len(x) != 1 for x in query.values()
                        ):
                            raise ValueError("INVALID_COMPARISON_QUERY")
                        result = compare_workflows(store, query["before"][0], query["after"][0])
                    elif parts == ["v1", "economic-results"]:
                        from .economic_cache import list_results

                        if set(query) - {"limit", "offset"} or any(
                            len(x) != 1 for x in query.values()
                        ):
                            raise ValueError("INVALID_ECONOMIC_QUERY")
                        result = list_results(store, limit=limit, offset=offset)
                    elif parts == ["v1", "economic-compare"]:
                        from .economic_cache import compare_cached

                        if set(query) != {"before", "after"} or any(
                            len(x) != 1 for x in query.values()
                        ):
                            raise ValueError("INVALID_ECONOMIC_QUERY")
                        result = compare_cached(store, query["before"][0], query["after"][0])
                    elif parts == ["v1", "impact"]:
                        from .insights import impact_preview

                        if (
                            set(query) != {"proposal"}
                            or len(query["proposal"]) != 1
                            or len(query["proposal"][0]) > 4096
                        ):
                            raise ValueError("INVALID_IMPACT_QUERY")

                        def unique(pairs):
                            value = {}
                            for key, item in pairs:
                                if key in value:
                                    raise ValueError("DUPLICATE_PROPOSAL_FIELD")
                                value[key] = item
                            return value

                        result = impact_preview(
                            store, json.loads(query["proposal"][0], object_pairs_hook=unique)
                        )
                    elif parts == ["v1", "history"]:
                        from .history import search_history

                        allowed = {
                            "q",
                            "classification",
                            "snapshot_sha256",
                            "limit",
                            "offset",
                            "source_kind",
                            "status",
                            "stage",
                            "decision",
                            "evidence_stage",
                            "topic_tags",
                            "reason_codes",
                            "revisit_conditions",
                        }
                        if set(query) - allowed or any(len(x) != 1 for x in query.values()):
                            raise ValueError("INVALID_HISTORY_QUERY")
                        values = {key: value[0] for key, value in query.items()}
                        result = search_history(
                            store,
                            q=values.pop("q", ""),
                            snapshot_sha256=values.pop("snapshot_sha256", None),
                            limit=int(values.pop("limit", "50")),
                            offset=int(values.pop("offset", "0")),
                            **values,
                        )
                    elif parts == ["v1", "evaluations"]:
                        from .analysis_reports import list_evaluations

                        if set(query) - {"limit"} or any(len(x) != 1 for x in query.values()):
                            raise ValueError("INVALID_EVALUATION_QUERY")
                        result = list_evaluations(store, int(query.get("limit", ["25"])[0]))
                    elif parts == ["v1", "workflows"]:
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
                        and parts[3] == "recheck"
                    ):
                        from .recheck import recheck_workflow

                        if query:
                            raise ValueError("INVALID_RECHECK_QUERY")
                        result = recheck_workflow(store, parts[2])
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
            except (ValueError, TypeError, RecursionError):
                if len(parts) > 1 and parts[1] in {
                    "compare",
                    "impact",
                    "history",
                    "evaluations",
                    "economic-results",
                    "economic-compare",
                }:
                    self.send_json(400, {"code": "INSIGHTS_REQUEST_REJECTED"})
                else:
                    self.send_json(404, {"code": "WORKFLOW_UNAVAILABLE"})
            except (OSError, sqlite3.Error):
                self.send_json(503, {"code": "DATABASE_UNAVAILABLE"})

        def do_POST(self):
            self.send_json(405, {"code": "READ_ONLY_API"})

        do_PUT = do_POST
        do_DELETE = do_POST
        do_PATCH = do_POST

    return Handler


def serve(database, host="127.0.0.1", port=8787, token_file=None):
    if not ipaddress.ip_address(host).is_loopback or ":" in host:
        raise ValueError("IPV4_LOOPBACK_REQUIRED")
    with Store(database, readonly=True):
        pass
    with HTTPServer(
        (host, port), handler_for(database, token=read_token(token_file) if token_file else None)
    ) as server:
        server.serve_forever()
