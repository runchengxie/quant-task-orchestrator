"""Read-only byte verification through the sealed raw-observation Owner CLI."""

from pathlib import Path

from .contracts import SHA, exact, file_sha


def arguments(binding):
    return [
        "contract",
        "verify-observation",
        "--root",
        binding["root"],
        "--expected-manifest-sha256",
        binding["expected_manifest_sha256"],
        "--max-content-bytes",
        str(binding["max_content_bytes"]),
        "--max-files",
        str(binding["max_files"]),
    ]


def validate(binding, receipt):
    if (
        receipt.get("schema") != "quant.raw_observation_assessment.v1"
        or receipt.get("manifest_sha256") != binding["expected_manifest_sha256"]
        or receipt.get("data_content_integrity") != "passed"
        or receipt.get("historical_pit") != "unknown"
        or receipt.get("derived_materialization") != "absent"
        or receipt.get("research_ready") is not False
        or receipt.get("time_basis") != "UTC"
        or not isinstance(receipt.get("content_snapshot_sha256"), str)
        or not SHA.fullmatch(receipt["content_snapshot_sha256"])
    ):
        raise ValueError("INVALID_RAW_OBSERVATION_RECEIPT")
    for field, ceiling in (
        ("file_count", binding["max_files"]),
        ("content_bytes", binding["max_content_bytes"]),
    ):
        if type(receipt.get(field)) is not int or not 0 <= receipt[field] <= ceiling:
            raise ValueError("RAW_OBSERVATION_BUDGET_MISMATCH")
    if (
        binding.get("content_snapshot_sha256")
        and binding["content_snapshot_sha256"] != receipt["content_snapshot_sha256"]
    ):
        raise ValueError("OWNER_IDENTITY_MISMATCH")
    return receipt


def observe(binding, caller=None):
    from .owners import Owner

    for path, expected in binding["pins"].items():
        if file_sha(path) != expected:
            raise ValueError("OWNER_BINDING_CHANGED")
    return validate(binding, (caller or Owner(binding)).call(arguments(binding)))


def bind_raw(adapter):
    exact(
        adapter,
        {"kind", "command", "root", "expected_manifest_sha256", "max_content_bytes", "max_files"},
    )
    command = adapter["command"]
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(a, str) and a for a in command)
    ):
        raise ValueError("INVALID_OWNER_COMMAND")
    if not isinstance(adapter["expected_manifest_sha256"], str) or not SHA.fullmatch(
        adapter["expected_manifest_sha256"]
    ):
        raise ValueError("INVALID_MANIFEST_DIGEST")
    for field in ("max_content_bytes", "max_files"):
        if type(adapter[field]) is not int or adapter[field] <= 0:
            raise ValueError("INVALID_CONTENT_CEILING")
    paths = [
        command[0],
        str(Path(adapter["root"]) / "manifest.yml"),
        str(Path(adapter["root"]) / "OBSERVATION_SEALED.json"),
    ]
    paths += [a for a in command[1:] if a.endswith(".py")]
    if not all(Path(p).is_absolute() and Path(p).is_file() for p in paths):
        raise ValueError("ABSOLUTE_OWNER_INPUT_REQUIRED")
    binding = {**adapter, "pins": {p: file_sha(p) for p in paths}}
    if (
        binding["pins"][str(Path(adapter["root"]) / "manifest.yml")]
        != binding["expected_manifest_sha256"]
    ):
        raise ValueError("MANIFEST_DIGEST_MISMATCH")
    result = observe(binding)
    binding["content_snapshot_sha256"] = result["content_snapshot_sha256"]
    return binding


def grade_raw(binding, receipt):
    validate(binding, receipt)
    return "SUCCEEDED", receipt["content_snapshot_sha256"], "RAW_CONTENT_VERIFIED"


def evidence_raw(binding, receipt):
    validate(binding, receipt)
    return {
        "input_integrity": {
            "status": "verified",
            "source": "quant-market-data-platform",
            "evidence_sha256": receipt["content_snapshot_sha256"],
        }
    }
