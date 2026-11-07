"""Bounded Research CLI lifecycle adapter; no direct model commands or qualification."""

import math
from pathlib import Path

from .contracts import SHA, digest, exact, file_sha, identifier, read_json

ACTIVE = {"admitted", "running", "cancel_requested"}
TERMINAL = {"completed", "failed", "cancelled", "timed_out", "owner_lost"}
USAGE = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")


def _pins(binding):
    for path, expected in binding["pins"].items():
        if file_sha(path) != expected:
            raise ValueError("OWNER_BINDING_CHANGED")


def _terminal(binding, receipt):
    path = Path(receipt.get("receipt", ""))
    sha = receipt.get("receipt_sha256")
    if not path.is_absolute() or not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise ValueError("INVALID_CODEX_RECEIPT_IDENTITY")
    output = Path(binding["output_directory"]).resolve()
    if output not in path.resolve().parents:
        raise ValueError("CODEX_RECEIPT_OUTSIDE_APPROVED_OUTPUT")
    if file_sha(path) != sha:
        raise ValueError("CODEX_RECEIPT_HASH_MISMATCH")
    original = read_json(path)
    for key, value in original.items():
        if key not in {"receipt", "receipt_sha256"} and receipt.get(key) != value:
            raise ValueError("CODEX_RECEIPT_BODY_MISMATCH")
    for key in (
        "owner_id",
        "plan_sha256",
        "status",
        "turn",
        "session",
        "observed_tokens",
        "cumulative_tokens",
        "usage",
        "config_sha256",
        "executable_sha256",
        "events_sha256",
    ):
        if original.get(key) != receipt.get(key):
            raise ValueError("CODEX_RECEIPT_BODY_MISMATCH")
    if (
        receipt.get("schema") != "research.codex-task-receipt/v1"
        or receipt.get("config_sha256") != binding["owner_plan_sha256"]
        or receipt.get("executable_sha256") != binding["executable_sha256"]
    ):
        raise ValueError("CODEX_CONFIGURATION_MISMATCH")
    events_sha = receipt.get("events_sha256")
    if receipt["status"] == "completed" and (events_sha is None or receipt.get("session") is None):
        raise ValueError("INCOMPLETE_CODEX_TERMINAL_IDENTITY")
    if events_sha is not None:
        if not isinstance(events_sha, str) or not SHA.fullmatch(events_sha):
            raise ValueError("INVALID_CODEX_EVENTS_DIGEST")
        if file_sha(path.with_suffix(".events.jsonl")) != events_sha:
            raise ValueError("CODEX_EVENTS_HASH_MISMATCH")
    return receipt


def validate_codex(binding, receipt):
    if (
        receipt.get("owner_id") != binding["key"]
        or receipt.get("plan_sha256") != binding["owner_plan_sha256"]
        or receipt.get("turn") != binding["target_turn"]
        or type(receipt.get("turn")) is not int
        or receipt.get("status") not in ACTIVE | TERMINAL
    ):
        raise ValueError("CODEX_OWNER_IDENTITY_MISMATCH")
    session = receipt.get("session")
    if session is not None:
        identifier(session)
    if binding.get("action") in {"resume", "observe"} and session != binding["session_id"]:
        raise ValueError("CODEX_RESUME_SESSION_MISMATCH")
    if receipt["status"] in TERMINAL:
        _terminal(binding, receipt)
    return receipt


def bind_codex(adapter):
    from .owners import Owner

    exact(adapter, {"kind", "command", "config", "key", "action", "session_id", "receipt"})
    identifier(adapter["key"])
    if adapter["action"] not in {"start", "resume", "observe"}:
        raise ValueError("INVALID_CODEX_ACTION")
    command = adapter["command"]
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(x, str) and x for x in command)
    ):
        raise ValueError("INVALID_OWNER_COMMAND")
    files = [command[0], adapter["config"], *[x for x in command[1:] if x.endswith(".py")]]
    if not all(Path(p).is_absolute() and Path(p).is_file() for p in files):
        raise ValueError("ABSOLUTE_OWNER_INPUT_REQUIRED")
    config = read_json(adapter["config"])
    if config.get("schema") not in {"research.codex-task/v1", "research.codex-task/v2"}:
        raise ValueError("UNSUPPORTED_CODEX_CONFIG")
    policy = "tool-free-read-only"
    if config["schema"] == "research.codex-task/v2":
        profile = config.get("tool_profile")
        if not isinstance(profile, str) or not Path(profile).is_absolute():
            raise ValueError("ABSOLUTE_TOOL_PROFILE_REQUIRED")
        if file_sha(profile) != config.get("tool_profile_sha256"):
            raise ValueError("TOOL_PROFILE_HASH_MISMATCH")
        for key in ("tool_gateway_sha256", "tool_python_sha256"):
            if not isinstance(config.get(key), str) or not SHA.fullmatch(config[key]):
                raise ValueError("EXACT_TOOL_HASH_REQUIRED")
        files.append(profile)
        policy = "research-read-only"
    for field in ("executable", "prompt_file"):
        path = config.get(field)
        if not isinstance(path, str) or not Path(path).is_absolute() or not Path(path).is_file():
            raise ValueError("ABSOLUTE_CODEX_INPUT_REQUIRED")
        files.append(path)
    if file_sha(config["executable"]) != config.get("executable_sha256") or file_sha(
        config["prompt_file"]
    ) != config.get("prompt_sha256"):
        raise ValueError("CODEX_INPUT_HASH_MISMATCH")
    binding = {
        **adapter,
        "pins": {p: file_sha(p) for p in files},
        "owner_plan_sha256": digest(config),
        "executable_sha256": config["executable_sha256"],
        "target_turn": 1,
        "output_directory": config["output_directory"],
    }
    plan = Owner(binding).call(["--config", adapter["config"], "plan"])
    if (
        plan.get("plan_sha256") != binding["owner_plan_sha256"]
        or plan.get("config_sha256") != binding["owner_plan_sha256"]
        or plan.get("config") != config
        or plan.get("tool_policy") != policy
    ):
        raise ValueError("INVALID_CODEX_OWNER_PLAN")
    if config["schema"] == "research.codex-task/v2" and (
        plan.get("tool_profile_sha256") != config["tool_profile_sha256"]
        or type(plan.get("tool_call_limit_per_turn")) is not int
        or plan["tool_call_limit_per_turn"] != 32
    ):
        raise ValueError("INVALID_TOOL_OWNER_PLAN")
    if adapter["action"] == "start":
        if adapter["session_id"] is not None or adapter["receipt"] is not None:
            raise ValueError("START_CANNOT_SELECT_SESSION")
    else:
        identifier(adapter["session_id"])
        path = Path(adapter["receipt"])
        if not path.is_absolute() or not path.is_file():
            raise ValueError("ABSOLUTE_PRIOR_RECEIPT_REQUIRED")
        prior = read_json(path)
        binding["target_turn"] = prior.get("turn")
        prior.update(receipt=str(path), receipt_sha256=file_sha(path))
        validate_codex({**binding, "action": "start"}, prior)
        if prior["status"] != "completed" or prior["session"] != adapter["session_id"]:
            raise ValueError("INVALID_PRIOR_CODEX_RECEIPT")
        if adapter["action"] == "resume":
            binding["target_turn"] += 1
        binding["pins"][str(path)] = file_sha(path)
        if prior.get("events_sha256"):
            events = path.with_suffix(".events.jsonl")
            binding["pins"][str(events)] = file_sha(events)
    return binding


def dispatch(binding, operation, caller=None):
    from .owners import Owner

    _pins(binding)
    if binding["action"] == "observe":
        receipt = read_json(binding["receipt"])
        receipt.update(receipt=binding["receipt"], receipt_sha256=file_sha(binding["receipt"]))
        return validate_codex(binding, receipt)
    actual = binding["action"] if operation == "start" else operation
    args = ["--config", binding["config"], actual, "--key", binding["key"]]
    if actual in {"start", "resume"}:
        args += ["--expected-plan-sha256", binding["owner_plan_sha256"]]
    if actual == "resume":
        args += ["--session", binding["session_id"], "--receipt", binding["receipt"]]
    receipt = (caller or Owner(binding)).call(args)
    return validate_codex(binding, receipt)


def grade_codex(binding, receipt):
    validate_codex(binding, receipt)
    status = receipt["status"]
    state = (
        "RUNNING"
        if status in ACTIVE
        else "SUCCEEDED"
        if status == "completed"
        else "CANCELLED"
        if status == "cancelled"
        else "FAILED"
    )
    return (
        state,
        receipt["owner_id"],
        "CODEX_TURN_COMPLETED" if status == "completed" else "NOT_VERIFIED",
    )


def execution_codex(binding, receipt):
    validate_codex(binding, receipt)
    raw_usage = receipt.get("usage")
    if raw_usage is not None and not isinstance(raw_usage, dict):
        raise ValueError("INVALID_CODEX_USAGE")
    usage = {key: (raw_usage or {}).get(key) for key in USAGE}
    for value in [
        *usage.values(),
        receipt.get("observed_tokens"),
        receipt.get("cumulative_tokens"),
    ]:
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("INVALID_CODEX_USAGE")
    observed, cumulative = receipt.get("observed_tokens"), receipt.get("cumulative_tokens")
    if observed is not None and all(
        usage[key] is not None for key in ("input_tokens", "output_tokens")
    ):
        if observed != usage["input_tokens"] + usage["output_tokens"]:
            raise ValueError("CODEX_USAGE_TOTAL_MISMATCH")
    if cumulative is not None and observed is not None and cumulative < observed:
        raise ValueError("CODEX_CUMULATIVE_USAGE_MISMATCH")
    seconds = receipt.get("cumulative_wall_seconds")
    if seconds is not None and (
        type(seconds) not in {int, float} or not math.isfinite(seconds) or seconds < 0
    ):
        raise ValueError("INVALID_CODEX_WALL_MEASUREMENT")
    return {
        "schema": "quant.codex_execution.v1",
        "owner_id": receipt["owner_id"],
        "owner_plan_sha256": binding["owner_plan_sha256"],
        "session_id": receipt.get("session"),
        "turn": receipt["turn"],
        "status": receipt["status"],
        "usage": usage,
        "observed_tokens": receipt.get("observed_tokens"),
        "cumulative_tokens": receipt.get("cumulative_tokens"),
        "cumulative_wall_seconds": seconds,
        "receipt_sha256": receipt.get("receipt_sha256"),
        "events_sha256": receipt.get("events_sha256"),
        "model_cost_usd": None,
        "runtime_jobs_cancelled": False,
    }


def project_execution(value):
    """Revalidate the stored public allowlist; private owner fields never survive."""
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("schema") != "quant.codex_execution.v1":
        raise ValueError("INVALID_EXECUTION_SNAPSHOT")
    identifier(value.get("owner_id"))
    if value.get("session_id") is not None:
        identifier(value["session_id"])
    if (
        type(value.get("turn")) is not int
        or value["turn"] < 1
        or value.get("status") not in ACTIVE | TERMINAL
    ):
        raise ValueError("INVALID_EXECUTION_SNAPSHOT")
    for field in ("owner_plan_sha256", "receipt_sha256", "events_sha256"):
        sha = value.get(field)
        if sha is not None and (not isinstance(sha, str) or not SHA.fullmatch(sha)):
            raise ValueError("INVALID_EXECUTION_DIGEST")
    raw = value.get("usage") or {}
    if not isinstance(raw, dict):
        raise ValueError("INVALID_CODEX_USAGE")
    usage = {key: raw.get(key) for key in USAGE}
    for number in [*usage.values(), value.get("observed_tokens"), value.get("cumulative_tokens")]:
        if number is not None and (type(number) is not int or number < 0):
            raise ValueError("INVALID_CODEX_USAGE")
    wall = value.get("cumulative_wall_seconds")
    if wall is not None and (type(wall) not in {int, float} or not math.isfinite(wall) or wall < 0):
        raise ValueError("INVALID_CODEX_WALL_MEASUREMENT")
    fields = (
        "schema",
        "owner_id",
        "owner_plan_sha256",
        "session_id",
        "turn",
        "status",
        "observed_tokens",
        "cumulative_tokens",
        "cumulative_wall_seconds",
        "receipt_sha256",
        "events_sha256",
    )
    return {
        **{key: value.get(key) for key in fields},
        "usage": usage,
        "model_cost_usd": None,
        "runtime_jobs_cancelled": False,
    }
