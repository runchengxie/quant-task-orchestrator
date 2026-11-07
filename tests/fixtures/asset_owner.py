"""Synthetic public-contract fixtures; no Owner implementation imports."""

import hashlib
import json
import sys
from pathlib import Path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def data_fixture(root):
    root = Path(root).resolve()
    target = root / "daily-v1"
    target.mkdir()
    manifest = target / "manifest.yml"
    manifest.write_text("dataset: daily\nstatus: completed\n")
    alias = root / "daily-current"
    alias.symlink_to(target, target_is_directory=True)
    contract = root / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "contract": {
                    "name": "synthetic",
                    "market": "a_share",
                    "provider": "tushare",
                    "version": 1,
                    "artifacts_root": str(root),
                },
                "assets": {
                    "daily": {
                        "alias_path": str(alias),
                        "manifest_path": str(alias / "manifest.yml"),
                        "exists": True,
                        "as_of": "20261030",
                        "manifest": {"status": "completed"},
                    }
                },
            }
        )
    )
    adapter = {
        "kind": "data",
        "command": [sys.executable],
        "artifacts_root": str(root),
        "contract": str(contract),
        "asset": ["daily"],
        "target_date": "20261030",
        "require_start_date": None,
    }
    snapshot = {
        "schema_version": "marketdata.asset-snapshot.v1",
        "contract_path": str(contract),
        "contract_sha256": sha(contract),
        "integrity_scope": "manifest_identity",
        "data_content_verified": False,
        "atomic_transaction": False,
        "assets": [
            {
                "asset_key": "daily",
                "manifest_path": str(manifest),
                "manifest_sha256": sha(manifest),
                "resolved_path": str(target),
            }
        ],
    }
    checks = [
        {
            "id": "daily:" + scope,
            "asset_key": "daily",
            "scope": scope,
            "outcome": "passed"
            if scope in ("freshness", "manifest_identity", "publication_complete")
            else "unknown",
        }
        for scope in (
            "freshness",
            "manifest_identity",
            "publication_complete",
            "data_content_integrity",
            "historical_pit",
            "contiguous_coverage",
        )
    ]
    return adapter, {
        "schema": "quant.data_assessment.v1",
        "snapshot": snapshot,
        "checks": checks,
        "research_ready": False,
        "legacy_quality_verdict": {},
        "limitations": [],
    }


def report_fixture(root):
    root = Path(root).resolve()
    payload = {
        "schema_version": "1.0",
        "as_of": "2026-10-02T23:00:00+00:00",
        "generated_at": "2026-10-03T00:00:00+00:00",
        "run_id": "synthetic-report",
        "facts": [],
        "events": [],
        "claims": [],
        "sections": [],
        "source_status": {},
        "missing_sources": ["research"],
        "quality_summary": {"status": "degraded"},
    }
    # Owner's documented legacy digest normalizes timestamp strings via datetime.
    # These canonical +00:00 timestamps need only the ISO separator normalization
    # used by datetime.__str__ when serialized through default=str.
    normalized = {
        **payload,
        "content_hash": None,
        "as_of": payload["as_of"].replace("T", " "),
        "generated_at": payload["generated_at"].replace("T", " "),
    }
    payload["content_hash"] = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    source = root / "daily_report.json"
    source.write_text(json.dumps(payload))
    manifest = root / "publication.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "publication": "public",
                "report_file": source.name,
                "run_id": payload["run_id"],
                "content_hash": payload["content_hash"],
                "report_sha256": sha(source),
            }
        )
    )
    adapter = {
        "kind": "report",
        "command": [sys.executable],
        "input": str(source),
        "manifest": str(manifest),
        "expected_date": "2026-10-02",
        "previous_report": None,
    }
    receipt = {
        "schema_version": "quant.market_brief.v1",
        "report_date": "2026-10-02",
        "as_of": payload["as_of"],
        "generated_at": payload["generated_at"],
        "source": {"report_file": source.name, "run_id": payload["run_id"]},
        "artifact_hash": sha(source),
        "content_hash": payload["content_hash"],
        "data_quality": payload["quality_summary"],
        "evidence_level": "descriptive",
        "limitations": ["Synthetic fixture"],
        "report": payload,
    }
    return adapter, receipt
