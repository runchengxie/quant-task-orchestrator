"""End-to-end CLI operations use only temporary state and local Git fixtures."""

import contextlib
import hashlib
import io
import json
import subprocess
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import test_coordinator

from quant_task_orchestrator.cli import main


class OperationsCliTests(unittest.TestCase):
    def invoke(self, args, expected=0):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = main([str(arg) for arg in args])
        self.assertEqual(code, expected, error.getvalue())
        text = (output if code == 0 else error).getvalue()
        self.assertTrue(
            text, f"stdout={output.getvalue()!r} stderr={error.getvalue()!r} code={code!r}"
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            self.fail(repr(text))

    def test_service_and_release_without_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = self.invoke(
                [
                    "service-unit",
                    "--release",
                    root / "release",
                    "--data-root",
                    root / "data",
                    "--config-root",
                    root / "config",
                ]
            )
            self.assertIn("127.0.0.1", result["unit"])
            wheel = root / "fixture.whl"
            wheel.write_bytes(b"wheel")
            sha = hashlib.sha256(b"wheel").hexdigest()
            staged = self.invoke(
                [
                    "release-stage",
                    "--wheel",
                    wheel,
                    "--sha256",
                    sha,
                    "--revision",
                    "a" * 40,
                    "--releases",
                    root / "releases",
                ]
            )
            self.assertFalse(staged["activated"])

    def test_inbox_run_and_local_outbox(self):
        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        try:
            wid = fixture.submit(False)
            root = fixture.store.path.parent
            inbox = root / "cli-inbox"
            inbox.mkdir()
            ledger = root / "cli-ledger.sqlite"
            event = dict(
                schema="quant.workflow_event.v1",
                event_id="cli-event",
                workflow_id=wid,
                source="owner",
                type="owner.changed",
            )
            (inbox / "event.json").write_text(json.dumps(event))
            prefix = ["--database", fixture.store.path]
            self.assertEqual(
                self.invoke([*prefix, "inbox", "--inbox", inbox, "--ledger", ledger])["accepted"], 1
            )
            run = self.invoke([*prefix, "run", "--once", "--inbox", inbox, "--ledger", ledger])
            self.assertEqual(run["inbox"]["duplicates"], 1)
            one = self.invoke(
                [
                    *prefix,
                    "outbox-enqueue",
                    wid,
                    "--ledger",
                    ledger,
                    "--action-signature",
                    "inspect",
                ]
            )
            items = self.invoke(["outbox-list", "--ledger", ledger])["notifications"]
            self.assertEqual(len(items), 1)
            self.assertNotIn("title", items[0])
            self.invoke(["outbox-ack", one["notification_id"], "--ledger", ledger])
            self.assertEqual(self.invoke(["outbox-list", "--ledger", ledger])["notifications"], [])
            self.invoke([*prefix, "run", "--once", "--inbox", inbox], expected=1)
        finally:
            fixture.doCleanups()

    def test_exact_catalog_skill_install_without_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            content = b"locked text\n"
            (repo / "SKILL.md").write_bytes(content)
            git("add", "SKILL.md")
            git("commit", "-qm", "fixture")
            skill = dict(
                id="fixture",
                owner_repo="owner/repo",
                source=str(repo),
                revision=git("rev-parse", "HEAD"),
                path="SKILL.md",
                sha256=hashlib.sha256(content).hexdigest(),
                permissions=["read"],
                input_contract="in.v1",
                output_contract="out.v1",
            )
            config = root / "config.json"
            config.write_text(
                json.dumps(
                    dict(schema="quant.orchestrator_config.v1", adapters={}, catalog=[skill])
                )
            )
            result = self.invoke(
                [
                    "skill-install",
                    "--config",
                    config,
                    "--skill-id",
                    "fixture",
                    "--destination",
                    root / "installed",
                ]
            )
            self.assertFalse(result["receipt"]["permission_grant"])
            self.assertEqual(Path(result["path"]).read_bytes(), content)
            self.invoke(
                [
                    "skill-install",
                    "--config",
                    config,
                    "--skill-id",
                    "missing",
                    "--destination",
                    root / "other",
                ],
                expected=1,
            )

    def test_backup_and_authenticated_health_without_global_database(self):
        from quant_task_orchestrator.api import handler_for

        fixture = test_coordinator.CoordinatorTests(
            "test_idempotency_conflict_and_read_after_restart"
        )
        fixture.setUp()
        server = None
        try:
            root = fixture.store.path.parent
            backup = self.invoke(
                [
                    "backup",
                    "--source",
                    fixture.store.path,
                    "--destination",
                    root / "cli-backup.sqlite",
                ]
            )
            self.assertEqual(backup["integrity"], "ok")
            token = "x" * 40
            token_file = root / "cli.token"
            token_file.write_text(token)
            token_file.chmod(0o600)
            server = ThreadingHTTPServer(
                ("127.0.0.1", 0), handler_for(fixture.store.path, token=token)
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            result = self.invoke(
                [
                    "health",
                    "--url",
                    f"http://127.0.0.1:{server.server_port}/v1/health",
                    "--token-file",
                    token_file,
                ]
            )
            self.assertTrue(result["healthy"])
            self.invoke(
                ["health", "--url", f"http://127.0.0.1:{server.server_port}/v1/health"], expected=1
            )
        finally:
            if server:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
            fixture.doCleanups()
