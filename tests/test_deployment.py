import hashlib
import json
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from quant_task_orchestrator.deployment import (
    backup_database,
    service_unit,
    stage_release,
    verify_health,
)


class DeploymentTests(unittest.TestCase):
    def test_stage_pins_digest_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wheel = root / "app.whl"
            wheel.write_bytes(b"wheel")
            sha = hashlib.sha256(b"wheel").hexdigest()
            release = stage_release(wheel, sha, "a" * 40, root / "releases")
            self.assertTrue((Path(release["release"]) / "app.whl").is_file())
            with self.assertRaises(FileExistsError):
                stage_release(wheel, sha, "a" * 40, root / "releases")
            with self.assertRaises(ValueError):
                stage_release(wheel, "b" * 64, "a" * 40, root / "other")

    def test_unit_is_readonly_and_backup_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            unit = service_unit(root / "release", root / "data", root / "config")
            self.assertIn("127.0.0.1", unit)
            self.assertIn("ProtectSystem=strict", unit)
            self.assertIn("--token-file", unit)
            db = root / "db.sqlite"
            with closing(sqlite3.connect(db)) as conn:
                with conn:
                    conn.execute("CREATE TABLE sample(id INTEGER)")
                    conn.execute("INSERT INTO sample VALUES(1)")
            result = backup_database(db, root / "backup.sqlite")
            self.assertEqual(result["integrity"], "ok")
            with self.assertRaises(FileExistsError):
                backup_database(db, root / "backup.sqlite")

    @unittest.skipUnless(shutil.which("systemd-analyze"), "systemd parser unavailable")
    def test_generated_unit_passes_real_systemd_parser_with_spaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            release = root / "release space"
            executable = release / "venv/bin/quant-task"
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o700)
            unit = root / "workbench.service"
            unit.write_text(service_unit(release, root / "data space", root / "config space"))
            result = subprocess.run(
                ["systemd-analyze", "verify", "--man=no", str(unit)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_service_rejects_relative_paths_and_injection(self):
        with self.assertRaises(ValueError):
            service_unit("relative", "/data", "/config")
        with self.assertRaises(ValueError):
            service_unit("/release\nExecStart=bad", "/data", "/config")
        with self.assertRaises(ValueError):
            service_unit("/release", "/data", "/config", port=80)

    def test_unit_quotes_spaces_and_rejects_specifiers_and_controls(self):
        unit = service_unit("/release space", "/data space", "/config space")
        self.assertIn('ExecStart="/release space/venv/bin/quant-task"', unit)
        self.assertIn('--database "/data space/quant/quant-task-orchestrator/state.sqlite"', unit)
        self.assertIn('ReadOnlyPaths="/data space" "/config space" "/release space"', unit)
        for invalid in ("/bad%h", "/bad${HOME}", "/bad\tvalue", "/bad\x00value", "/bad\x7fvalue"):
            with self.subTest(path=repr(invalid)), self.assertRaises(ValueError):
                service_unit(invalid, "/data", "/config")

    def test_health_requires_exact_workbench_schema_from_real_http_server(self):
        class Handler(BaseHTTPRequestHandler):
            payload = {"wrong_service": True}

            def do_GET(self):
                body = json.dumps(self.payload).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_port}/v1/health"
            with self.assertRaises(ValueError):
                verify_health(url)
            Handler.payload = dict(
                schema="quant.workbench_health.v1",
                status="ok",
                mode="read_only",
                authentication_required=True,
            )
            self.assertTrue(verify_health(url)["healthy"])
            Handler.payload["mode"] = "read_write"
            with self.assertRaises(ValueError):
                verify_health(url)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
