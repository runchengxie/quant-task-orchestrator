"""Read-only arithmetic over explicitly pinned Owner-declared financial receipts.

Matching declarations establish a comparison basis, not independent provenance,
market truth, causal attribution, research qualification or promotion authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

HASH_FIELDS = (
    "data_sha256",
    "universe_sha256",
    "benchmark_sha256",
    "cost_model_sha256",
    "execution_semantics_sha256",
    "metric_definitions_sha256",
)
BASIS_FIELDS = HASH_FIELDS + (
    "sample_start",
    "sample_end",
    "time_zone",
    "currency",
    "return_frequency",
    "history_visibility",
)
METRICS = (
    "total_return",
    "annualized_return",
    "max_drawdown",
    "annualized_volatility",
    "sharpe",
    "turnover",
)
FIELDS = {
    "schema",
    "owner",
    "source_revision",
    "result_id",
    "report_sha256",
    "evidence_class",
    "execution_status",
    "admission_status",
    "basis",
    "metrics",
}


def _hex(value, length=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + "}", value)


def _choice(value, choices):
    return isinstance(value, str) and value in choices


def _shape(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError("INVALID_ECONOMIC_RESULT_SHAPE")


def validate_result(value):
    """Validate a deliberately small public envelope; unknown basis stays null."""
    _shape(value, FIELDS)
    if (
        value["schema"] != "quant.economic_result.v1"
        or value["owner"] != "quant-research"
        or not _hex(value["source_revision"], 40)
        or not _hex(value["result_id"])
        or not _hex(value["report_sha256"])
        or not _choice(value["evidence_class"], {"synthetic", "historical_mechanism", "research"})
        or not _choice(value["execution_status"], {"succeeded", "failed", "unknown"})
        or not _choice(value["admission_status"], {"blocked", "not_assessed", "owner_declared"})
    ):
        raise ValueError("INVALID_ECONOMIC_RESULT_IDENTITY")
    basis = value["basis"]
    _shape(basis, BASIS_FIELDS)
    for key in HASH_FIELDS:
        if basis[key] is not None and not _hex(basis[key]):
            raise ValueError("INVALID_ECONOMIC_BASIS_HASH")
    for key in ("sample_start", "sample_end"):
        if basis[key] is not None:
            try:
                if (
                    not isinstance(basis[key], str)
                    or date.fromisoformat(basis[key]).isoformat() != basis[key]
                ):
                    raise ValueError("INVALID_ECONOMIC_SAMPLE")
            except (ValueError, TypeError) as error:
                raise ValueError("INVALID_ECONOMIC_SAMPLE") from error
    if (
        basis["sample_start"]
        and basis["sample_end"]
        and basis["sample_start"] > basis["sample_end"]
    ):
        raise ValueError("INVALID_ECONOMIC_SAMPLE")
    if basis["time_zone"] is not None:
        try:
            if not isinstance(basis["time_zone"], str) or len(basis["time_zone"]) > 100:
                raise ValueError("INVALID_ECONOMIC_TIME_ZONE")
            ZoneInfo(basis["time_zone"])
        except (ValueError, TypeError, ZoneInfoNotFoundError) as error:
            raise ValueError("INVALID_ECONOMIC_TIME_ZONE") from error
    if basis["currency"] is not None and (
        not isinstance(basis["currency"], str) or not re.fullmatch("[A-Z]{3}", basis["currency"])
    ):
        raise ValueError("INVALID_ECONOMIC_CURRENCY")
    if (
        basis["return_frequency"] is not None
        and not _choice(basis["return_frequency"], {"daily", "weekly", "monthly"})
        or basis["history_visibility"] is not None
        and not _choice(basis["history_visibility"], {"seen", "holdout", "prospective"})
    ):
        raise ValueError("INVALID_ECONOMIC_SAMPLE_BASIS")
    _shape(value["metrics"], METRICS)
    for name, metric in value["metrics"].items():
        if metric is None:
            continue
        if type(metric) not in {int, float} or abs(metric) > 1e12 or not math.isfinite(metric):
            raise ValueError("INVALID_ECONOMIC_METRIC")
        if (
            name in {"total_return", "annualized_return"}
            and metric < -1
            or name == "max_drawdown"
            and not 0 <= metric <= 1
            or name in {"annualized_volatility", "turnover"}
            and metric < 0
        ):
            raise ValueError("INVALID_ECONOMIC_METRIC_CONVENTION")
    return value


def load_result(path, expected_sha256):
    """Read the hash-checked regular file through non-symlink directory handles."""
    if not _hex(expected_sha256):
        raise ValueError("INVALID_ECONOMIC_RESULT_PIN")
    path = Path(path).absolute()
    if ".." in path.parts:
        raise ValueError("INVALID_ECONOMIC_RESULT_PATH")
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in path.parts[1:-1]:
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
            )
            os.close(directory)
            directory = child
        descriptor = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
    finally:
        os.close(directory)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 1_048_576:
            raise ValueError("INVALID_ECONOMIC_RESULT_FILE")
        body = source.read(1_048_577)
    if len(body) > 1_048_576 or hashlib.sha256(body).hexdigest() != expected_sha256:
        raise ValueError("ECONOMIC_RESULT_PIN_MISMATCH")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_ECONOMIC_JSON_KEY")
            result[key] = value
        return result

    try:
        result = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")),
        )
    except (RecursionError, UnicodeError) as error:
        raise ValueError("INVALID_ECONOMIC_RESULT_JSON") from error
    return validate_result(result)


def compare_results(before, after):
    """Compare only identical, fully populated declarations. Never infer causality."""
    before, after = validate_result(before), validate_result(after)
    reasons = []
    for key in BASIS_FIELDS:
        left, right = before["basis"][key], after["basis"][key]
        if left is None or right is None:
            reasons.append("MISSING_BASIS:" + key)
        elif left != right:
            reasons.append("BASIS_MISMATCH:" + key)
    if before["execution_status"] != "succeeded" or after["execution_status"] != "succeeded":
        reasons.append("EXECUTION_NOT_SUCCEEDED")
    if before["evidence_class"] != after["evidence_class"]:
        reasons.append("EVIDENCE_CLASS_MISMATCH")
    if not any(
        before["metrics"][key] is not None and after["metrics"][key] is not None for key in METRICS
    ):
        reasons.append("MISSING_METRIC_PAIRS")
    metrics = {}
    if not reasons:
        for key in METRICS:
            left, right = before["metrics"][key], after["metrics"][key]
            metrics[key] = {
                "before": left,
                "after": right,
                "delta": right - left if left is not None and right is not None else None,
            }
    return {
        "schema": "quant.economic_comparison.v1",
        "status": "not_comparable" if reasons else "comparable",
        "basis_authority": "owner_declared",
        "before_result_id": before["result_id"],
        "after_result_id": after["result_id"],
        "evidence_class": before["evidence_class"]
        if before["evidence_class"] == after["evidence_class"]
        else None,
        "before_admission_status": before["admission_status"],
        "after_admission_status": after["admission_status"],
        "reasons": reasons,
        "metrics": metrics,
        "provenance_verified": False,
        "research_validated": False,
        "promotion_authorized": False,
        "causal_attribution": False,
        "metric_convention": "returns_volatility_and_turnover_are_ratios_drawdown_is_positive_loss_fraction",
    }
