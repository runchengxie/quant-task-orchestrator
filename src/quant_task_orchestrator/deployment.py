"""Offline immutable release staging, service proposals and verified SQLite backup.

Staging is not installation or activation. No service manager commands run here.
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .event_inbox import safe_path


def _hex(value, length):
    if not isinstance(value, str) or not re.fullmatch(rf"[0-9a-f]{{{length}}}", value):
        raise ValueError("INVALID_PIN")


def stage_release(wheel, sha256, revision, releases):
    """Stage a prebuilt wheel pinned to a caller-verified merged source revision."""
    _hex(sha256, 64)
    _hex(revision, 40)
    wheel = safe_path(wheel)
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise ValueError("INVALID_WHEEL")
    releases = safe_path(releases)
    releases.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = releases / (revision + "-" + sha256[:16])
    if target.exists():
        raise FileExistsError("RELEASE_EXISTS")
    temporary = Path(tempfile.mkdtemp(prefix=".staging-", dir=releases))
    try:
        staged = temporary / wheel.name
        shutil.copyfile(wheel, staged)
        with staged.open("rb") as stream:
            actual_digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual_digest != sha256:
            raise ValueError("WHEEL_DIGEST_MISMATCH")
        manifest = dict(
            schema="quant.release.v1",
            revision=revision,
            wheel=wheel.name,
            sha256=sha256,
            installed=False,
            activated=False,
        )
        (temporary / "release.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
        for child in temporary.iterdir():
            child.chmod(0o400)
            with child.open("rb") as stream:
                os.fsync(stream.fileno())
        # mkdir reserves destination; rename cannot silently replace another release.
        target.mkdir(mode=0o700)
        for child in temporary.iterdir():
            os.rename(child, target / child.name)
        temporary.rmdir()
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return dict(release=str(target), **manifest)


def _unit_path(path):
    if not Path(path).is_absolute():
        raise ValueError("ABSOLUTE_SERVICE_PATH_REQUIRED")
    path = safe_path(path)
    if any(ord(char) < 32 or ord(char) == 127 or char in '$%"\\' for char in str(path)):
        raise ValueError("INVALID_SERVICE_PATH")
    return str(path)


def service_unit(release, data_root, config_root, *, port=8787):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("INVALID_PORT")
    release, data, config = map(_unit_path, (release, data_root, config_root))
    return f'''[Unit]
Description=Quant orchestrator read-only local GUI
After=network.target

[Service]
Type=simple
ExecStart="{release}/venv/bin/quant-task" --database "{data}/quant/quant-task-orchestrator/state.sqlite" serve-api --host 127.0.0.1 --port {port} --token-file "{config}/projects/quant-task-orchestrator/gui.token"
WorkingDirectory="{release}"
Restart=on-failure
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true
ReadOnlyPaths="{data}" "{config}" "{release}"

[Install]
WantedBy=default.target
'''


def backup_database(source, destination):
    source, destination = safe_path(source), safe_path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(destination)) as backup:
                original.backup(backup)
                integrity = backup.execute("PRAGMA integrity_check").fetchone()[0]
                if integrity != "ok":
                    raise ValueError("BACKUP_INTEGRITY_FAILED")
        with destination.open("rb") as stream:
            sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
        return dict(integrity="ok", sha256=sha256, path=str(destination))
    except BaseException:
        destination.unlink()
        raise


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def verify_health(url, *, token=None):
    """Probe explicit loopback health only; never forward credentials on redirects."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or parsed.username
        or parsed.password
    ):
        raise ValueError("HEALTH_REQUIRES_LOOPBACK")
    headers = {"Authorization": "Bearer " + token} if token else {}
    try:
        response = build_opener(_NoRedirect).open(Request(url, headers=headers), timeout=5)
    except HTTPError as error:
        error.close()
        raise ValueError("HEALTH_FAILED") from None
    with response:
        body = response.read(65537)
        if response.status != 200 or len(body) > 65536:
            raise ValueError("HEALTH_FAILED")
        payload = json.loads(body)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema", "status", "mode", "authentication_required"}
            or payload["schema"] != "quant.workbench_health.v1"
            or payload["status"] != "ok"
            or payload["mode"] != "read_only"
            or type(payload["authentication_required"]) is not bool
        ):
            raise ValueError("HEALTH_FAILED")
    return dict(healthy=True, transport="loopback_http")
