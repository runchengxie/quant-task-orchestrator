"""Optional private read-only API authentication. Never print credential values."""

import hmac
import os
import re
import stat
from pathlib import Path


def read_token(path):
    source = Path(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        descriptor = os.open(source, flags)
    except OSError:
        raise ValueError("PRIVATE_TOKEN_UNAVAILABLE") from None
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError("PRIVATE_TOKEN_PERMISSIONS_REQUIRED")
        value = stream.read(258).decode("ascii").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", value):
        raise ValueError("INVALID_PRIVATE_TOKEN")
    return value


def authorized(header, token):
    if token is None:
        return True
    return (
        isinstance(header, str)
        and header.isascii()
        and hmac.compare_digest(header, "Bearer " + token)
    )
