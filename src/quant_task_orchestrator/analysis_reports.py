"""Explicitly recorded trace scores; never publish a model-quality assertion."""

import json
import unicodedata

from .contracts import SHA, canonical, digest
from .evaluation import default_suite, evaluate_trace, reference_trace

CRITERIA = ("required_observation", "call_budget", "no_forbidden_calls")
UNCERTAINTY = [
    "Recorded observations are unverified inputs; no model was invoked.",
    "Passing checks does not establish market truth or general agent reliability.",
]
INCOMPLETE = "Token usage is incomplete."


def _count(value, maximum):
    return type(value) is int and 0 <= value <= maximum


def _validate_report(report):
    """Validate the complete derived schema; a digest is identity, not authority."""
    suite = default_suite()
    if not isinstance(report, dict) or set(report) != set(evaluate_trace(reference_trace())):
        raise ValueError("INVALID_CACHED_EVALUATION")
    if report["suite_version"] != suite["version"]:
        raise ValueError("INVALID_CACHED_EVALUATION")
    model = report["reported_model"]
    if model is not None and (
        not isinstance(model, str)
        or not 1 <= len(model) <= 160
        or any(unicodedata.category(c).startswith("C") for c in model)
    ):
        raise ValueError("INVALID_CACHED_EVALUATION")
    cases = report["cases"]
    if not isinstance(cases, list) or len(cases) != len(suite["cases"]):
        raise ValueError("INVALID_CACHED_EVALUATION")
    calls, passed, forbidden_cases, forbidden_capacity = 0, 0, 0, 0
    for case, definition in zip(cases, suite["cases"], strict=True):
        if (
            not isinstance(case, dict)
            or set(case) != {"id", "passed", "criteria", "missing_evidence", "tool_calls"}
            or case["id"] != definition["id"]
        ):
            raise ValueError("INVALID_CACHED_EVALUATION")
        criteria = case["criteria"]
        if (
            not isinstance(criteria, dict)
            or set(criteria) != set(CRITERIA)
            or any(type(v) is not bool for v in criteria.values())
            or type(case["passed"]) is not bool
            or not _count(case["tool_calls"], 1000)
        ):
            raise ValueError("INVALID_CACHED_EVALUATION")
        number = case["tool_calls"]
        if (
            case["passed"] != all(criteria.values())
            or case["missing_evidence"] != [key for key in CRITERIA if not criteria[key]]
            or criteria["call_budget"] != (0 < number <= definition["max_calls"])
            or (
                not number
                and (criteria["required_observation"] or not criteria["no_forbidden_calls"])
            )
        ):
            raise ValueError("INVALID_CACHED_EVALUATION")
        calls += number
        passed += case["passed"]
        if not criteria["no_forbidden_calls"]:
            forbidden_cases += 1
            forbidden_capacity += number
    if (
        not _count(report["passed"], len(cases))
        or report["passed"] != passed
        or type(report["total"]) is not int
        or report["total"] != len(cases)
        or not _count(report["tool_calls"], 10000)
        or report["tool_calls"] != calls
        or report["unknown_cases"] != []
    ):
        raise ValueError("INVALID_CACHED_EVALUATION")
    for key in ("tool_failures", "human_takeovers", "forbidden_calls", "unknown_usage_events"):
        if not _count(report[key], calls):
            raise ValueError("INVALID_CACHED_EVALUATION")
    if not forbidden_cases <= report["forbidden_calls"] <= forbidden_capacity:
        raise ValueError("INVALID_CACHED_EVALUATION")
    known = report["known_token_subtotal"]
    unknown = report["unknown_usage_events"]
    if not _count(known, (calls - unknown) * 10**12):
        raise ValueError("INVALID_CACHED_EVALUATION")
    incomplete = report["observed_tokens"] is None
    if (
        report["uncertainty"] != UNCERTAINTY + ([INCOMPLETE] if incomplete else [])
        or ((unknown or not calls) and not incomplete)
        or (incomplete and not unknown and calls and all(case["tool_calls"] for case in cases))
        or (
            not incomplete
            and (
                not _count(report["observed_tokens"], 10**16) or report["observed_tokens"] != known
            )
        )
    ):
        raise ValueError("INVALID_CACHED_EVALUATION")


def record_evaluation(store, trace):
    if store.readonly:
        raise ValueError("READ_ONLY_STORE")
    report = evaluate_trace(trace)
    identity = digest(report)
    with store.db:
        store.db.execute(
            "INSERT OR IGNORE INTO evaluation_reports VALUES(?,?)", (identity, canonical(report))
        )
    return report


def list_evaluations(store, limit=25):
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("INVALID_EVALUATION_LIMIT")
    exists = store.db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evaluation_reports'"
    ).fetchone()
    result = {"schema": "quant.evaluation_list.v1", "reports": []}
    if not exists:
        return result
    for identity, payload in store.db.execute(
        "SELECT report_sha256,payload FROM evaluation_reports ORDER BY rowid DESC LIMIT ?", (limit,)
    ):

        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("DUPLICATE_EVALUATION_FIELD")
                value[key] = item
            return value

        if not isinstance(payload, str) or len(payload) > 1_048_576:
            raise ValueError("INVALID_CACHED_EVALUATION")
        try:
            report = json.loads(
                payload,
                object_pairs_hook=unique,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_EVALUATION")),
            )
        except RecursionError as exc:
            raise ValueError("INVALID_CACHED_EVALUATION") from exc
        if not isinstance(report, dict) or set(report) != set(evaluate_trace(reference_trace())):
            raise ValueError("INVALID_CACHED_EVALUATION")
        _validate_report(report)
        if (
            report.get("schema") != "quant.agent_evaluation.v1"
            or report.get("suite_sha256") != digest(default_suite())
            or report.get("model_evaluated") is not False
            or report.get("provenance_verified") is not False
            or not isinstance(report.get("evaluation_scope"), str)
            or report.get("evaluation_scope") not in {"reference-not-model", "recorded-trace-only"}
        ):
            raise ValueError("INVALID_CACHED_EVALUATION")
        if any(
            not isinstance(report.get(key), str) or not SHA.fullmatch(report[key])
            for key in ("suite_sha256", "trace_sha256")
        ):
            raise ValueError("INVALID_CACHED_EVALUATION")
        if digest(report) != identity:
            raise ValueError("INVALID_CACHED_EVALUATION")
        result["reports"].append(report)
    return result
