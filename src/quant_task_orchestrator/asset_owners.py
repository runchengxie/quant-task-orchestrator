"""Fixed read-only adapters for published data and verified report Owners.

Owners validate business contracts. This boundary checks envelope identities and
pins, then projects six evidence dimensions without exposing report contents.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import date
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{64}\Z")
SOURCES = {"data": "quant-market-data-platform", "report": "quant-intel-platform"}
DIMENSIONS = (
    "input_integrity",
    "historical_pit",
    "execution_semantics",
    "independent_review",
    "economic_conclusion",
    "promotion",
)


def _sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _path(value, *, directory=False):
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise ValueError("ABSOLUTE_OWNER_INPUT_REQUIRED")
    if not (Path(value).is_dir() if directory else Path(value).is_file()):
        raise ValueError("OWNER_INPUT_MISSING")
    return value


def _date(value, compact=False):
    if value is None:
        return
    if not isinstance(value, str):
        raise ValueError("INVALID_OWNER_DATE")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError("INVALID_OWNER_DATE") from None
    if parsed.strftime("%Y%m%d") != value if compact else parsed.isoformat() != value:
        raise ValueError("INVALID_OWNER_DATE")


def _verify(binding):
    for path, expected in binding["pins"].items():
        try:
            same = _sha(path) == expected
        except OSError:
            same = False
        if not same:
            raise ValueError("OWNER_BINDING_CHANGED")


def _arguments(binding):
    if binding["kind"] == "report":
        args = [
            "--input",
            binding["input"],
            "--manifest",
            binding["manifest"],
            "--expected-date",
            binding["expected_date"],
        ]
        if binding["previous_report"] is not None:
            args += ["--previous-report", binding["previous_report"]]
        return args
    args = [
        "contract",
        "assess",
        "--artifacts-root",
        binding["artifacts_root"],
        "--current-contract",
        binding["contract"],
    ]
    for asset in binding["asset"]:
        args += ["--asset", asset]
    for key, flag in [
        ("target_date", "--target-date"),
        ("require_start_date", "--require-start-date"),
    ]:
        if binding[key] is not None:
            args += [flag, binding[key]]
    return args


def _validate(binding, receipt, *, initial=False):
    if not isinstance(receipt, dict):
        raise ValueError("INVALID_ASSET_OWNER_RECEIPT")
    if binding["kind"] == "report":
        source = receipt.get("source")
        if (
            receipt.get("schema_version") != "quant.market_brief.v1"
            or receipt.get("evidence_level") != "descriptive"
            or not isinstance(receipt.get("report"), dict)
            or not isinstance(receipt.get("data_quality"), dict)
            or not isinstance(receipt.get("limitations"), list)
            or not isinstance(source, dict)
            or not isinstance(source.get("run_id"), str)
            or not source["run_id"]
            or not isinstance(receipt.get("content_hash"), str)
            or not SHA.fullmatch(receipt["content_hash"])
        ):
            raise ValueError("INVALID_ASSET_OWNER_RECEIPT")
        if (
            receipt.get("artifact_hash") != binding["pins"][binding["input"]]
            or receipt.get("report_date") != binding["expected_date"]
            or source.get("report_file") != Path(binding["input"]).name
        ):
            raise ValueError("OWNER_IDENTITY_MISMATCH")
        identity = {
            key: receipt[key] for key in ("artifact_hash", "content_hash", "source", "report_date")
        }
    else:
        snapshot = receipt.get("snapshot")
        checks = receipt.get("checks")
        if (
            receipt.get("schema") != "quant.data_assessment.v1"
            or receipt.get("research_ready") is not False
            or not isinstance(snapshot, dict)
            or snapshot.get("schema_version") != "marketdata.asset-snapshot.v1"
            or snapshot.get("integrity_scope") != "manifest_identity"
            or snapshot.get("data_content_verified") is not False
            or snapshot.get("atomic_transaction") is not False
            or not isinstance(snapshot.get("assets"), list)
            or not isinstance(checks, list)
            or not checks
        ):
            raise ValueError("INVALID_ASSET_OWNER_RECEIPT")
        if snapshot.get("contract_sha256") != binding["pins"][binding["contract"]] or snapshot.get(
            "contract_path"
        ) != str(Path(binding["contract"]).resolve()):
            raise ValueError("OWNER_IDENTITY_MISMATCH")
        seen = set()
        for ref in snapshot["assets"]:
            if (
                not isinstance(ref, dict)
                or ref.get("asset_key") not in binding["asset"]
                or ref["asset_key"] in seen
                or not isinstance(ref.get("manifest_sha256"), str)
                or not SHA.fullmatch(ref["manifest_sha256"])
            ):
                raise ValueError("INVALID_ASSET_OWNER_RECEIPT")
            seen.add(ref["asset_key"])
            manifest = _path(ref.get("manifest_path"))
            # Only published metadata inside the explicitly authorized root is read.
            if (
                not Path(manifest)
                .resolve()
                .is_relative_to(Path(binding["artifacts_root"]).resolve())
            ):
                raise ValueError("OWNER_IDENTITY_MISMATCH")
            if _sha(manifest) != ref["manifest_sha256"]:
                raise ValueError("OWNER_BINDING_CHANGED")
            if initial:
                binding["pins"][manifest] = ref["manifest_sha256"]
            elif binding["pins"].get(manifest) != ref["manifest_sha256"]:
                raise ValueError("OWNER_IDENTITY_MISMATCH")
        if seen != set(binding["asset"]):
            raise ValueError("OWNER_IDENTITY_MISMATCH")
        ids = set()
        for check in checks:
            if (
                not isinstance(check, dict)
                or check.get("asset_key") not in seen
                or not isinstance(check.get("id"), str)
                or check["id"] in ids
                or not isinstance(check.get("scope"), str)
                or check.get("outcome") not in ("passed", "failed", "unknown")
            ):
                raise ValueError("INVALID_ASSET_OWNER_RECEIPT")
            ids.add(check["id"])
        for asset in seen:
            for scope in (
                "freshness",
                "manifest_identity",
                "publication_complete",
                "data_content_integrity",
                "historical_pit",
                "contiguous_coverage",
            ):
                if sum(c["asset_key"] == asset and c["scope"] == scope for c in checks) != 1:
                    raise ValueError("INVALID_ASSET_OWNER_RECEIPT")
        identity = snapshot
    fingerprint = _digest(identity)
    if not initial and binding.get("asset_identity") != fingerprint:
        raise ValueError("OWNER_IDENTITY_MISMATCH")
    return fingerprint


def bind_asset(adapter):
    """Validate explicit arguments and freeze Owner-validated metadata identity."""
    if not isinstance(adapter, dict) or adapter.get("kind") not in SOURCES:
        raise ValueError("UNREGISTERED_ADAPTER_KIND")
    kind = adapter["kind"]
    fields = (
        {
            "kind",
            "command",
            "artifacts_root",
            "contract",
            "asset",
            "target_date",
            "require_start_date",
        }
        if kind == "data"
        else {"kind", "command", "input", "manifest", "expected_date", "previous_report"}
    )
    if set(adapter) != fields:
        raise ValueError("INVALID_ASSET_ADAPTER_FIELDS")
    binding = copy.deepcopy(adapter)
    command = binding["command"]
    if (
        not isinstance(command, list)
        or not 1 <= len(command) <= 2
        or not all(isinstance(arg, str) and arg for arg in command)
    ):
        raise ValueError("INVALID_OWNER_COMMAND")
    _path(command[0])
    if len(command) == 2 and not command[1].endswith(".py"):
        raise ValueError("INVALID_OWNER_COMMAND")
    pins = {_path(arg): _sha(arg) for arg in command}
    if kind == "data":
        _path(binding["artifacts_root"], directory=True)
        assets = binding["asset"]
        if (
            not isinstance(assets, list)
            or not 1 <= len(assets) <= 50
            or not all(isinstance(a, str) and re.fullmatch(r"[A-Za-z0-9_.-]+", a) for a in assets)
            or len(set(assets)) != len(assets)
        ):
            raise ValueError("INVALID_OWNER_ASSETS")
        for key in ("target_date", "require_start_date"):
            _date(binding[key], compact=True)
        inputs = [binding["contract"]]
    else:
        if binding["expected_date"] is None:
            raise ValueError("INVALID_OWNER_DATE")
        _date(binding["expected_date"])
        inputs = [binding["input"], binding["manifest"]]
        if binding["previous_report"] is not None:
            inputs.append(binding["previous_report"])
    for value in inputs:
        pins[_path(value)] = _sha(value)
    binding["pins"] = pins
    from .owners import Owner

    receipt = Owner(binding).call(_arguments(binding), accepted=(0, 1) if kind == "data" else (0,))
    binding["asset_identity"] = _validate(binding, receipt, initial=True)
    _verify(binding)
    return binding


def start_asset(binding, caller=None):
    """Recheck immutable inputs and ask the same read-only Owner operation."""
    from .owners import Owner

    _verify(binding)
    receipt = (caller or Owner(binding)).call(
        _arguments(binding), accepted=(0, 1) if binding["kind"] == "data" else (0,)
    )
    _validate(binding, receipt)
    _verify(binding)
    return receipt


def grade_asset(binding, receipt):
    _verify(binding)
    _validate(binding, receipt)
    if binding["kind"] == "report":
        return "SUCCEEDED", receipt["artifact_hash"], "REPORT_INTEGRITY_VERIFIED"
    required = {"freshness", "manifest_identity", "publication_complete"}
    ready = not any(c["outcome"] == "failed" for c in receipt["checks"]) and all(
        c["outcome"] == "passed" for c in receipt["checks"] if c["scope"] in required
    )
    return (
        "SUCCEEDED" if ready else "BLOCKED",
        binding["asset_identity"],
        "PUBLICATION_METADATA_VERIFIED" if ready else "NOT_VERIFIED",
    )


def evidence_asset(binding, receipt):
    status, _, _ = grade_asset(binding, receipt)
    source = SOURCES[binding["kind"]]
    evidence = {name: {"status": "unknown", "source": source} for name in DIMENSIONS}
    # Metadata identity is scoped: never promote Owner's deliberately unknown PIT,
    # byte integrity, economics, independent review or publication delivery.
    evidence["input_integrity"] = {
        "status": "verified"
        if binding["kind"] == "report" and status == "SUCCEEDED"
        else "unknown",
        "source": source,
        "evidence_sha256": (
            receipt["artifact_hash"] if binding["kind"] == "report" else binding["asset_identity"]
        ),
    }
    return evidence
