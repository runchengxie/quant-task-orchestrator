"""Catalog locking must reject oversized blobs before buffering their content."""

import contextlib
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from quant_task_orchestrator.cli import main


class SkillCatalogBoundsTests(unittest.TestCase):
    def test_cli_rejects_large_catalog_blob_before_git_show(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

            git("init", "-q")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            content = b"x" * (1_048_576 + 1)
            (repo / "SKILL.md").write_bytes(content)
            git("add", "SKILL.md")
            git("commit", "-qm", "oversized fixture")
            entry = dict(
                id="oversized",
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
                    dict(
                        schema="quant.orchestrator_config.v1",
                        adapters={},
                        catalog=[entry],
                    )
                )
            )
            original_run = subprocess.run

            def no_blob_read(command, *args, **kwargs):
                if "show" in command:
                    self.fail("oversized blob reached buffered git show")
                return original_run(command, *args, **kwargs)

            output, error = io.StringIO(), io.StringIO()
            with (
                patch("subprocess.run", no_blob_read),
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(error),
            ):
                code = main(
                    [
                        "skill-install",
                        "--config",
                        str(config),
                        "--skill-id",
                        "oversized",
                        "--destination",
                        str(root / "installed"),
                    ]
                )
            self.assertEqual(code, 1)
            self.assertFalse(output.getvalue())
            self.assertNotIn(str(root), error.getvalue())
            self.assertFalse((root / "installed").exists())

    def test_exact_commit_ignores_local_git_replacement_objects(self):
        from quant_task_orchestrator.contracts import lock_skill

        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

            git("init", "-q")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.invalid")
            original = b"original exact-commit content\n"
            (repo / "SKILL.md").write_bytes(original)
            git("add", "SKILL.md")
            git("commit", "-qm", "original")
            revision = git("rev-parse", "HEAD")
            (repo / "SKILL.md").write_text("local replacement content\n")
            git("commit", "-qam", "replacement")
            git("replace", revision, git("rev-parse", "HEAD"))
            entry = dict(
                id="locked",
                owner_repo="owner/repo",
                source=str(repo),
                revision=revision,
                path="SKILL.md",
                sha256=hashlib.sha256(original).hexdigest(),
                permissions=["read"],
                input_contract="in.v1",
                output_contract="out.v1",
            )
            self.assertEqual(lock_skill(entry), entry)
