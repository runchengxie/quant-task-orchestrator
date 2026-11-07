"""Install one locked Git blob as inert Skill text, with an explicit trust receipt."""

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import PurePosixPath

from .event_inbox import safe_path


def install_skill(
    repo,
    revision,
    path,
    sha256,
    destination,
    *,
    owner_repo,
    permissions,
    input_contract,
    output_contract,
):
    if not re.fullmatch("[0-9a-f]{40}", revision) or not re.fullmatch("[0-9a-f]{64}", sha256):
        raise ValueError("EXACT_REVISION_AND_DIGEST_REQUIRED")
    relative = PurePosixPath(path)
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or not relative.parts
        or relative.name != "SKILL.md"
        or ":" in path
        or "\\" in path
    ):
        raise ValueError("INVALID_SKILL_PATH")
    if not all(
        isinstance(value, str) and 0 < len(value) <= 300
        for value in (owner_repo, input_contract, output_contract)
    ):
        raise ValueError("INVALID_SKILL_CONTRACT")
    if not isinstance(permissions, list) or not all(
        isinstance(value, str) and 0 < len(value) <= 100 for value in permissions
    ):
        raise ValueError("INVALID_SKILL_PERMISSIONS")
    repo = safe_path(repo)

    def git(*args):
        return subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repo), *args], stderr=subprocess.DEVNULL
        )

    if git("rev-parse", "--verify", revision + "^{commit}").decode().strip() != revision:
        raise ValueError("INVALID_REVISION")
    tree = git("ls-tree", revision, "--", path).decode().split("\t", 1)[0].split()
    if not tree or tree[0] != "100644" or tree[1] != "blob":
        raise ValueError("SKILL_MUST_BE_REGULAR_TEXT")
    size = int(git("cat-file", "-s", revision + ":" + path))
    if size > 1024 * 1024:
        raise ValueError("SKILL_TOO_LARGE")
    content = git("show", revision + ":" + path)
    content.decode("utf-8")
    if hashlib.sha256(content).hexdigest() != sha256:
        raise ValueError("SKILL_DIGEST_MISMATCH")
    receipt = dict(
        schema="quant.skill_install.v1",
        owner_repo=owner_repo,
        revision=revision,
        source_path=path,
        sha256=sha256,
        permissions=permissions,
        input_contract=input_contract,
        output_contract=output_contract,
        executed=False,
        permission_grant=False,
        support_files_installed=False,
    )
    destination = safe_path(destination)
    if destination.is_relative_to(repo):
        raise ValueError("DESTINATION_MUST_BE_EXTERNAL")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = destination / sha256
    # Reserve name atomically. Existing content is never trusted or overwritten.
    target.mkdir(mode=0o700)
    try:
        with (target / "SKILL.md").open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        (target / "SKILL.md").chmod(0o400)
        with (target / "receipt.json").open("x") as stream:
            json.dump(receipt, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        (target / "receipt.json").chmod(0o400)
    except BaseException:
        shutil.rmtree(target)
        raise
    return dict(path=str(target / "SKILL.md"), receipt=receipt)
