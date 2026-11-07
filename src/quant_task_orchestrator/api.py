"""Loopback-only, read-only query API for both operator interfaces."""

import ipaddress
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

from .store import Store


def handler_for(database):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_json(self, status, payload):
            body = json.dumps(payload, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            url = urlsplit(self.path)
            parts = url.path.strip("/").split("/")
            try:
                with Store(database, readonly=True) as store:
                    if parts == ["v1", "workflows"]:
                        result = {"schema": "quant.workflow_list.v1", "workflows": store.list()}
                    elif len(parts) == 3 and parts[:2] == ["v1", "workflows"]:
                        result = store.view(parts[2])
                    elif (
                        len(parts) == 4
                        and parts[:2] == ["v1", "workflows"]
                        and parts[3] == "events"
                    ):
                        after = int(parse_qs(url.query).get("after", ["0"])[0])
                        result = {
                            "schema": "quant.workflow_events.v1",
                            "events": store.events(parts[2], max(after, 0)),
                        }
                    else:
                        return self.send_json(404, {"code": "NOT_FOUND"})
                self.send_json(200, result)
            except (ValueError, OSError):
                self.send_json(404, {"code": "WORKFLOW_UNAVAILABLE"})

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
