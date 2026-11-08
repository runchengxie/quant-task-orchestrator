"""Bounded, read-only summaries of local shadow assessment records."""

import json
import math
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path

MAX_BYTES = 1_048_576
MAX_LIMIT = 1000
MAX_DURATION_SECONDS = 31 * 86400
SHA = re.compile(r"[0-9a-f]{64}\Z")
RUN = re.compile(r"[0-9a-f]{32}\Z")
STATUSES = {
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "BLOCKED",
    "UNKNOWN",
    "RUNNING",
    "PENDING",
    "APPROVED",
    "DISPATCHING",
    "NEEDS_RECONCILIATION",
    "CANCELLING",
    "AWAITING_APPROVAL",
    "AWAITING_EVENT",
    "ACTIVE",
}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("NONFINITE_JSON")
    return number


def _directory(path):
    # Every component is opened relative to an already-open descriptor. No symlink
    # races, glob expansion, recursive walk, or reads of workflow databases.
    absolute = Path(path).absolute()
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            if part in {".", ".."}:
                raise ValueError("INVALID_ROOT")
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def _record(root_fd, name):
    directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
    try:
        fd = os.open(
            "assessment.json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
                raise ValueError("INVALID_ASSESSMENT_FILE")
            body = stream.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("ASSESSMENT_TOO_LARGE")
        return json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_float=_finite_float,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")),
        )
    finally:
        os.close(directory)


def summarize_shadows(root, expected_config_sha256, *, limit=500):
    """Return safe metadata only; errors and incomplete enumeration fail closed.

    Each immediate child must be a UUID-hex run directory with assessment.json.
    No filesystem timestamps or directory names establish observation timing.
    """
    if not isinstance(expected_config_sha256, str) or not SHA.fullmatch(expected_config_sha256):
        raise ValueError("INVALID_EXPECTED_CONFIG_SHA256")
    if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
        raise ValueError("INVALID_HISTORY_LIMIT")
    counts = {name: 0 for name in sorted(STATUSES)}
    other_counts = {name: 0 for name in sorted(STATUSES)}
    errors = {}
    times, durations, seen = [], [], set()
    scanned = matched = mismatched = unknown_time = 0
    truncated = False

    def error(code):
        errors[code] = errors.get(code, 0) + 1

    try:
        root_fd = _directory(root)
    except (OSError, ValueError):
        root_fd = None
        error("ROOT_UNAVAILABLE_OR_UNSAFE")
    if root_fd is not None:
        try:
            with os.scandir(root_fd) as entries:
                for entry in entries:
                    if scanned >= limit:
                        truncated = True
                        error("ENTRY_LIMIT_EXCEEDED")
                        break
                    scanned += 1
                    try:
                        if not RUN.fullmatch(entry.name):
                            raise ValueError("INVALID_RUN_DIRECTORY")
                        record = _record(root_fd, entry.name)
                        if (
                            not isinstance(record, dict)
                            or record.get("schema") != "quant.data_shadow.v1"
                        ):
                            raise ValueError("INVALID_ASSESSMENT_SCHEMA")
                        run_id = record.get("run_id")
                        if run_id != entry.name or run_id in seen:
                            raise ValueError("INVALID_OR_DUPLICATE_RUN_ID")
                        seen.add(run_id)
                        sha = record.get("config_sha256")
                        if not isinstance(sha, str) or not SHA.fullmatch(sha):
                            raise ValueError("INVALID_CONFIG_SHA256")
                        status = record.get("status")
                        if not isinstance(status, str) or status not in STATUSES:
                            raise ValueError("INVALID_STATUS")
                        if (
                            record.get("shadow_only") is not True
                            or record.get("production_schedule_changed") is not False
                            or record.get("qualified_research_ready") is not False
                            or record.get("promotion_authorized") is not False
                            or type(record.get("new_model_calls")) is not int
                            or record["new_model_calls"] != 0
                        ):
                            raise ValueError("INVALID_SHADOW_BOUNDARY")
                        observed = record.get("observed_at")
                        timestamp = None
                        if observed is not None:
                            if not isinstance(observed, str) or len(observed) > 64:
                                raise ValueError("INVALID_OBSERVED_AT")
                            try:
                                timestamp = datetime.fromisoformat(observed.replace("Z", "+00:00"))
                                if timestamp.utcoffset() is None:
                                    raise ValueError()
                                timestamp = timestamp.astimezone(UTC)
                                if timestamp > datetime.now(UTC):
                                    raise ValueError()
                            except (ValueError, OverflowError):
                                raise ValueError("INVALID_OBSERVED_AT") from None
                        duration = record.get("duration_seconds")
                        if duration is not None and (
                            type(duration) not in {int, float}
                            or not 0 <= duration <= MAX_DURATION_SECONDS
                            or not math.isfinite(duration)
                        ):
                            raise ValueError("INVALID_DURATION_SECONDS")
                        if sha != expected_config_sha256:
                            mismatched += 1
                            other_counts[status] += 1
                            continue
                        matched += 1
                        counts[status] += 1
                        if timestamp is None:
                            unknown_time += 1
                        else:
                            times.append(timestamp)
                        if duration is not None:
                            durations.append(duration)
                    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
                        # Fixed codes only: exception messages may contain private paths.
                        error("INVALID_OR_UNREADABLE_ASSESSMENT")
        except OSError:
            error("DIRECTORY_READ_FAILED")
        finally:
            os.close(root_fd)
    span = (max(times) - min(times)).total_seconds() if times else None
    days = len({t.date() for t in times})
    sufficient = (
        not errors
        and not mismatched
        and not unknown_time
        and matched >= 7
        and counts["SUCCEEDED"] == matched
        and days >= 7
        and span is not None
        and span >= 7 * 86400
    )
    return {
        "schema": "quant.data_shadow_history.v1",
        "expected_config_sha256": expected_config_sha256,
        "shadow_only": True,
        "entries_scanned": scanned,
        "limit": limit,
        "truncated": truncated,
        "matched_assessments": matched,
        "other_config_assessments": mismatched,
        "other_config_status_counts": other_counts,
        "status_counts": counts,
        "failed_assessments": counts["FAILED"],
        "non_success_assessments": matched - counts["SUCCEEDED"],
        "errors": errors,
        "assessment_integrity": "invalid" if errors else "complete",
        "unknown_timestamp_assessments": unknown_time,
        "first_observed_at": min(times).isoformat() if times else None,
        "last_observed_at": max(times).isoformat() if times else None,
        "observed_span_seconds": span,
        "distinct_utc_dates": days,
        "measured_latency": {
            "samples": len(durations),
            "min_seconds": min(durations) if durations else None,
            "max_seconds": max(durations) if durations else None,
        },
        "observation_window": "sufficient" if sufficient else "insufficient",
        "minimum_window_seconds": 7 * 86400,
        "minimum_distinct_utc_dates": 7,
        "qualified_research_ready": False,
        "promotion_authorized": False,
        "production_schedule_changed": False,
    }
