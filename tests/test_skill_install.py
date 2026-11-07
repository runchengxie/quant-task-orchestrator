import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

from quant_task_orchestrator.skill_install import install_skill


class SkillInstallTests(unittest.TestCase):
    def test_exact_git_blob_installed_with_receipt_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

            git("init", "-q")
            git("config", "user.name", "Test")
            git("config", "user.email", "test@example.invalid")
            (repo / "SKILL.md").write_text("locked content\n")
            git("add", "SKILL.md")
            git("commit", "-qm", "fixture")
            revision = git("rev-parse", "HEAD")
            kwargs = dict(
                owner_repo="owner/repo",
                permissions=["read"],
                input_contract="in.v1",
                output_contract="out.v1",
            )
            sha = hashlib.sha256(b"locked content\n").hexdigest()
            result = install_skill(repo, revision, "SKILL.md", sha, root / "installed", **kwargs)
            self.assertEqual(Path(result["path"]).read_text(), "locked content\n")
            self.assertEqual(result["receipt"]["permissions"], ["read"])
            with self.assertRaises(FileExistsError):
                install_skill(repo, revision, "SKILL.md", sha, root / "installed", **kwargs)
            with self.assertRaises(ValueError):
                install_skill(repo, "HEAD", "../SKILL.md", sha, root / "other", **kwargs)
