"""Typed, conservative evidence projection; never forward raw Owner payloads."""

from .contracts import SHA
from .evidence_scope import assess_check, metadata

DIMENSIONS = (
    "input_integrity",
    "historical_pit",
    "execution_semantics",
    "independent_review",
    "economic_conclusion",
    "promotion",
)
SOURCES = {
    "quant-backtest-runtime",
    "quant-research",
    "quant-market-data-platform",
    "quant-intel-platform",
    "orchestrator",
}
STATUSES = {"verified", "missing", "unknown", "not_applicable"}


def project_evidence(kind, evidence_status, observed):
    source = {
        "runtime": "quant-backtest-runtime",
        "research": "quant-research",
        "native_session": "quant-research",
        "codex_task": "quant-research",
        "research_snapshot": "quant-research",
        "raw_observation": "quant-market-data-platform",
        "data": "quant-market-data-platform",
        "report": "quant-intel-platform",
    }.get(kind, "orchestrator")
    checks = {name: {"status": "unknown", "source": source} for name in DIMENSIONS}
    if kind == "runtime" and evidence_status == "RESULT_INTEGRITY_VERIFIED":
        checks["input_integrity"]["status"] = "verified"
    if kind == "research" and evidence_status == "DIAGNOSTIC_COMPLETED":
        checks["economic_conclusion"]["status"] = "not_applicable"
    if kind == "research" and evidence_status in {"SUPPORTED", "DISCARDED"}:
        checks["economic_conclusion"]["status"] = "verified"
    if isinstance(observed, dict):
        for name in DIMENSIONS:
            raw = observed.get(name)
            if name == "promotion" or name not in observed:
                continue
            if not isinstance(raw, dict):
                checks[name] = {"status": "unknown", "source": source, "metadata_invalid": True}
                continue
            status, owner, fingerprint = (
                raw.get("status"),
                raw.get("source"),
                raw.get("evidence_sha256"),
            )
            if (
                not isinstance(status, str)
                or not isinstance(owner, str)
                or status not in STATUSES
                or owner not in SOURCES
            ):
                checks[name] = {"status": "unknown", "source": source, "metadata_invalid": True}
                checks[name].update(metadata(raw))
                continue
            if fingerprint is not None and (
                not isinstance(fingerprint, str) or not SHA.fullmatch(fingerprint)
            ):
                checks[name] = {"status": "unknown", "source": source, "metadata_invalid": True}
                checks[name].update(metadata(raw))
                continue
            if owner != source and any(
                key in raw for key in ("scope", "assessed_at", "valid_until")
            ):
                # A source string cannot delegate scoped authority across owners.
                checks[name] = {"status": "unknown", "source": source, "metadata_invalid": True}
                checks[name].update(metadata(raw))
                continue
            checks[name] = {"status": status, "source": owner}
            if fingerprint:
                checks[name]["evidence_sha256"] = fingerprint
            checks[name].update(metadata(raw))
    # A coordination observation never grants promotion, regardless of an Owner claim.
    checks["promotion"] = {"status": "unknown", "source": "quant-research"}
    for name, check in checks.items():
        check["applicability"] = assess_check(check, dimension=name)
    return {"schema": "quant.evidence_view.v1", "checks": checks}
