"""Typed evidence applicability: market scope and assessment freshness are distinct."""

import re
from datetime import UTC, date, datetime

HASHES = ("data_sha256", "strategy_sha256", "universe_sha256")
CONTEXT = {*HASHES, "as_of", "sample_start", "sample_end"}
AUTHORITIES = {
    "input_integrity": {
        "quant-research",
        "quant-market-data-platform",
        "quant-backtest-runtime",
        "quant-intel-platform",
    },
    "historical_pit": {"quant-research", "quant-market-data-platform"},
    "execution_semantics": {"quant-research", "quant-backtest-runtime"},
    "independent_review": {"quant-research"},
    "economic_conclusion": {"quant-research"},
    "promotion": set(),
}


def timestamp(value):
    if not isinstance(value, str) or len(value) > 40:
        raise ValueError("INVALID_EVIDENCE_TIME")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)", value):
        raise ValueError("INVALID_EVIDENCE_TIME")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("UTC_EVIDENCE_TIME_REQUIRED")
    return parsed.astimezone(UTC)


def validate_context(value):
    if not isinstance(value, dict) or set(value) != CONTEXT:
        raise ValueError("INVALID_EVIDENCE_CONTEXT")
    for key in HASHES:
        if not isinstance(value[key], str) or not re.fullmatch("[0-9a-f]{64}", value[key]):
            raise ValueError("INVALID_EVIDENCE_FINGERPRINT")
    timestamp(value["as_of"])
    for key in ("sample_start", "sample_end"):
        if (
            not isinstance(value[key], str)
            or date.fromisoformat(value[key]).isoformat() != value[key]
        ):
            raise ValueError("INVALID_EVIDENCE_SAMPLE")
    if value["sample_start"] > value["sample_end"]:
        raise ValueError("INVALID_EVIDENCE_SAMPLE")
    return dict(value)


def metadata(raw):
    """Preserve only typed fields; remember malformed metadata after projection."""
    result = {}
    bad = raw.get("metadata_invalid") is True
    if "scope" in raw:
        try:
            result["scope"] = validate_context(raw["scope"])
        except (ValueError, TypeError, OverflowError):
            bad = True
    for key in ("assessed_at", "valid_until"):
        if key in raw:
            try:
                result[key] = timestamp(raw[key]).isoformat()
            except (ValueError, TypeError, OverflowError):
                bad = True
    if bad:
        result["metadata_invalid"] = True
    return result


def assess_check(check, context=None, *, now=None, dimension=None):
    now = datetime.now(UTC) if now is None else now
    if now.tzinfo is None:
        raise ValueError("AWARE_CLOCK_REQUIRED")

    def verdict(code, usable=False):
        return {"code": code, "usable": usable}

    if check.get("status") != "verified":
        return verdict("NOT_VERIFIED")
    if check.get("metadata_invalid"):
        return verdict("INVALID_METADATA")
    temporal = any(key in check for key in ("assessed_at", "valid_until"))
    scoped = "scope" in check
    if (
        (scoped or context is not None)
        and dimension is not None
        and check.get("source") not in AUTHORITIES.get(dimension, set())
    ):
        return verdict("UNSUITABLE_AUTHORITY")
    if temporal or scoped or context is not None:
        if not all(key in check for key in ("assessed_at", "valid_until")):
            return verdict("VALIDITY_UNAVAILABLE")
        try:
            assessed, until = timestamp(check["assessed_at"]), timestamp(check["valid_until"])
        except (ValueError, TypeError, OverflowError):
            return verdict("INVALID_VALIDITY")
        if until <= assessed:
            return verdict("INVALID_VALIDITY")
        if assessed > now:
            return verdict("ASSESSMENT_IN_FUTURE")
        if now >= until:
            return verdict("EXPIRED")
    if scoped:
        try:
            scope = validate_context(check["scope"])
        except (ValueError, TypeError, OverflowError):
            return verdict("INVALID_SCOPE")
    if context is not None:
        try:
            requested = validate_context(context)
        except (ValueError, TypeError, OverflowError):
            return verdict("INVALID_CONTEXT")
        if not scoped:
            return verdict("SCOPE_UNAVAILABLE")
        if not isinstance(check.get("evidence_sha256"), str) or not re.fullmatch(
            "[0-9a-f]{64}", check["evidence_sha256"]
        ):
            return verdict("EVIDENCE_IDENTITY_UNAVAILABLE")
        if any(scope[key] != requested[key] for key in HASHES):
            return verdict("IDENTITY_MISMATCH")
        if timestamp(scope["as_of"]) != timestamp(requested["as_of"]):
            return verdict("AS_OF_MISMATCH")
        if (
            scope["sample_start"] > requested["sample_start"]
            or scope["sample_end"] < requested["sample_end"]
        ):
            return verdict("SAMPLE_NOT_COVERED")
        return verdict("APPLICABLE", True)
    return verdict("CURRENT_UNSCOPED" if temporal else "LEGACY_UNSCOPED", True)
