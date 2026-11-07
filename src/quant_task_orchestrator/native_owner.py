"""Read-only attachment to an Owner-verified native session, never model launch."""

import math
from pathlib import Path

from .contracts import exact, file_sha, identifier


def _arguments(binding):
    args = [
        "--config",
        binding["config"],
        "--receipt",
        binding["receipt"],
        "--events",
        binding["events"],
        "--session",
        binding["session_id"],
    ]
    if binding.get("resume_receipt"):
        args += ["--resume-receipt", binding["resume_receipt"]]
    return args


def validate_native(binding, receipt):
    if (
        receipt.get("schema") != "quant.native_research_session_inspection.v1"
        or receipt.get("session_id") != binding["session_id"]
        or receipt.get("research_validated") is not False
        or receipt.get("promotion_authorized") is not False
        or type(receipt.get("execution_complete")) is not bool
        or receipt.get("execution_status") not in {"complete", "incomplete", "interrupted"}
        or (receipt["execution_complete"] != (receipt["execution_status"] == "complete"))
        or receipt.get("model_cost_usd") is not None
    ):
        raise ValueError("INVALID_NATIVE_OWNER_RECEIPT")
    for field in ("config", "receipt", "events"):
        if receipt.get(field + "_sha256") != binding["pins"][binding[field]]:
            raise ValueError("OWNER_IDENTITY_MISMATCH")
    if binding.get("resume_receipt") and (
        receipt.get("resume_verified") is not True
        or receipt.get("resume_receipt_sha256") != binding["pins"][binding["resume_receipt"]]
    ):
        raise ValueError("NATIVE_RESUME_BINDING_MISMATCH")
    tools = receipt.get("observed_tools")
    if not isinstance(tools, list) or any(
        t not in {"context", "readiness", "propose", "advance", "report", "handoff"} for t in tools
    ):
        raise ValueError("INVALID_NATIVE_TOOLS")
    wall = receipt.get("wall_seconds")
    if wall is not None and (type(wall) not in {int, float} or not math.isfinite(wall) or wall < 0):
        raise ValueError("INVALID_NATIVE_MEASUREMENT")
    return receipt


def bind_native(adapter):
    fields = {"kind", "command", "config", "receipt", "events", "session_id"}
    if "resume_receipt" in adapter:
        fields.add("resume_receipt")
    exact(adapter, fields)
    identifier(adapter["session_id"])
    command = adapter["command"]
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(x, str) and x for x in command)
    ):
        raise ValueError("INVALID_OWNER_COMMAND")
    files = [command[0], adapter["config"], adapter["receipt"], adapter["events"]]
    files += [x for x in command[1:] if x.endswith(".py")]
    if adapter.get("resume_receipt"):
        files.append(adapter["resume_receipt"])
    if not all(Path(p).is_absolute() and Path(p).is_file() for p in files):
        raise ValueError("ABSOLUTE_OWNER_INPUT_REQUIRED")
    binding = {**adapter, "pins": {p: file_sha(p) for p in files}}
    start_native(binding)
    return binding


def start_native(binding, caller=None):
    from .owners import Owner

    caller = caller or Owner(binding)
    for path, expected in binding["pins"].items():
        if file_sha(path) != expected:
            raise ValueError("OWNER_BINDING_CHANGED")
    receipt = caller.call(_arguments(binding))
    validate_native(binding, receipt)
    return receipt


def grade_native(binding, receipt):
    validate_native(binding, receipt)
    return (
        "SUCCEEDED" if receipt["execution_complete"] else "BLOCKED",
        receipt["session_id"],
        "NATIVE_SEGMENT_VERIFIED" if receipt["execution_complete"] else "NATIVE_SEGMENT_INCOMPLETE",
    )
