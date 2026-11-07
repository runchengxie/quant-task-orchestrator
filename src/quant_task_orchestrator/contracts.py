"""Strict workflow, source-lock and approval-plan contracts."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_sha(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def read_json(path):
    source = Path(path)
    if not source.is_file() or source.stat().st_size > 1_048_576:
        raise ValueError("JSON_FILE_UNAVAILABLE_OR_TOO_LARGE")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    return json.loads(
        source.read_text(),
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE_JSON")),
    )


def identifier(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise ValueError("INVALID_IDENTIFIER")
    return value


def exact(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError("INVALID_FIELDS")


def validate_workflow(workflow, config):
    fields = {"schema", "idempotency_key", "title", "steps"}
    if "trigger" in workflow:
        fields.add("trigger")
        exact(workflow["trigger"], {"source", "event_type"})
        identifier(workflow["trigger"]["source"])
        if workflow["trigger"]["event_type"] not in {
            "owner.changed",
            "data.published",
            "report.published",
        }:
            raise ValueError("INVALID_TRIGGER")
    exact(workflow, fields)
    exact(config, {"schema", "adapters", "catalog"})
    if (
        workflow["schema"] != "quant.workflow.v1"
        or config["schema"] != "quant.orchestrator_config.v1"
    ):
        raise ValueError("UNSUPPORTED_SCHEMA")
    identifier(workflow["idempotency_key"])
    if not isinstance(workflow["title"], str) or not 1 <= len(workflow["title"]) <= 160:
        raise ValueError("INVALID_TITLE")
    if not isinstance(config["adapters"], dict) or not isinstance(config["catalog"], list):
        raise ValueError("INVALID_CONFIG")
    steps = workflow["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 100:
        raise ValueError("INVALID_STEPS")
    seen = {}
    for step in steps:
        fields = {"id", "adapter", "depends_on", "skills"}
        if "requires_evidence" in step:
            fields.add("requires_evidence")
        exact(step, fields)
        requirements = step.get("requires_evidence", {})
        from .evidence import DIMENSIONS

        if not isinstance(requirements, dict) or any(
            dep not in step["depends_on"]
            or not isinstance(checks, list)
            or not checks
            or any(name not in DIMENSIONS for name in checks)
            for dep, checks in requirements.items()
        ):
            raise ValueError("INVALID_EVIDENCE_REQUIREMENTS")
        sid = identifier(step["id"])
        if sid in seen or step["adapter"] not in config["adapters"]:
            raise ValueError("DUPLICATE_STEP_OR_UNKNOWN_ADAPTER")
        for field in ("depends_on", "skills"):
            if not isinstance(step[field], list) or len(step[field]) > 100:
                raise ValueError("INVALID_STEP_LIST")
            for value in step[field]:
                identifier(value)
            if len(set(step[field])) != len(step[field]):
                raise ValueError("DUPLICATE_STEP_ITEM")
        seen[sid] = step
    done = set()
    while len(done) < len(seen):
        ready = {
            sid for sid, step in seen.items() if sid not in done and set(step["depends_on"]) <= done
        }
        if not ready:
            raise ValueError("CYCLIC_OR_MISSING_DEPENDENCY")
        done.update(ready)


def lock_skill(skill):
    exact(
        skill,
        {
            "id",
            "owner_repo",
            "source",
            "revision",
            "path",
            "sha256",
            "permissions",
            "input_contract",
            "output_contract",
        },
    )
    identifier(skill["id"])
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", skill["owner_repo"]):
        raise ValueError("INVALID_SKILL_OWNER")
    if not re.fullmatch(r"[0-9a-f]{40}", skill["revision"]) or not SHA.fullmatch(skill["sha256"]):
        raise ValueError("EXACT_SKILL_REVISION_AND_HASH_REQUIRED")
    path = PurePosixPath(skill["path"])
    if path.is_absolute() or ".." in path.parts or not path.parts or ":" in str(path):
        raise ValueError("INVALID_SKILL_PATH")
    if not Path(skill["source"]).is_absolute():
        raise ValueError("ABSOLUTE_SKILL_SOURCE_REQUIRED")
    if not isinstance(skill["permissions"], list) or not skill["permissions"]:
        raise ValueError("SKILL_PERMISSIONS_REQUIRED")
    for permission in skill["permissions"]:
        identifier(permission)
    for field in ("input_contract", "output_contract"):
        identifier(skill[field])

    def git(*arguments):
        return subprocess.run(
            ["git", "--no-replace-objects", "-C", skill["source"], *arguments],
            capture_output=True,
            timeout=15,
            check=True,
        ).stdout

    reference = f"{skill['revision']}:{path}"
    try:
        if git("cat-file", "-t", reference).strip() != b"blob":
            raise ValueError("SKILL_MUST_BE_BLOB")
        size = int(git("cat-file", "-s", reference))
        if not 0 <= size <= 1_048_576:
            raise ValueError("SKILL_TOO_LARGE")
        content = git("show", reference)
    except (subprocess.SubprocessError, OSError):
        raise ValueError("SKILL_SOURCE_UNAVAILABLE") from None
    if len(content) > 1_048_576 or hashlib.sha256(content).hexdigest() != skill["sha256"]:
        raise ValueError("SKILL_HASH_MISMATCH")
    return dict(skill)


def bind_adapter(adapter):
    from .adapters import ADAPTERS
    from .owners import Owner

    if not isinstance(adapter, dict):
        raise ValueError("INVALID_ADAPTER")
    adapter = dict(adapter)
    revision = adapter.pop("owner_revision", None)
    if revision is not None and (
        not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision)
    ):
        raise ValueError("EXACT_OWNER_REVISION_REQUIRED")
    kind = adapter.get("kind")
    if kind not in ADAPTERS:
        raise ValueError("UNREGISTERED_ADAPTER_KIND")
    if kind == "research_snapshot":
        from .research_snapshot import bind_snapshot

        result = bind_snapshot(adapter)
        if revision:
            result["owner_revision"] = revision
        return result
    if kind in {"raw_observation", "codex_task"}:
        if kind == "raw_observation":
            from .raw_owner import bind_raw

            result = bind_raw(adapter)
        else:
            from .codex_owner import bind_codex

            result = bind_codex(adapter)
        if revision:
            result["owner_revision"] = revision
        return result
    if kind in {"data", "report"}:
        from .asset_owners import bind_asset

        result = bind_asset(adapter)
        if revision:
            result["owner_revision"] = revision
        return result
    if kind == "native_session":
        from .native_owner import bind_native

        result = bind_native(adapter)
        if revision:
            result["owner_revision"] = revision
        return result
    expected = (
        {"kind", "command", "request", "queue"}
        if kind == "runtime"
        else {"kind", "command", "config", "proposal_id"}
    )
    if kind not in {"runtime", "research"}:
        raise ValueError("UNREGISTERED_ADAPTER_KIND")
    exact(adapter, expected)
    command = adapter["command"]
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(x, str) and x for x in command)
    ):
        raise ValueError("INVALID_OWNER_COMMAND")
    if not Path(command[0]).is_absolute() or not Path(command[0]).is_file():
        raise ValueError("ABSOLUTE_OWNER_EXECUTABLE_REQUIRED")
    # Executable and explicit interpreter scripts are immutable code pins.
    # Installed modules must live in an operator-managed immutable environment.
    pins = {command[0]: file_sha(command[0])}
    for argument in command[1:]:
        if argument.endswith(".py"):
            if not Path(argument).is_absolute():
                raise ValueError("ABSOLUTE_OWNER_SCRIPT_REQUIRED")
            pins[argument] = file_sha(argument)
    input_path = adapter["request" if kind == "runtime" else "config"]
    if not isinstance(input_path, str) or not Path(input_path).is_absolute():
        raise ValueError("ABSOLUTE_OWNER_INPUT_REQUIRED")
    pins[input_path] = file_sha(input_path)
    result = {**adapter, "pins": pins}
    if kind == "runtime":
        if type(adapter["queue"]) is not bool:
            raise ValueError("INVALID_QUEUE_FLAG")
        request = read_json(input_path)
        result["idempotency_key"] = identifier(request["idempotency_key"])
        owner_plan = Owner(result).call(["plan", input_path])
        plan_hash = owner_plan.get("plan_sha256")
        if not isinstance(plan_hash, str) or not SHA.fullmatch(plan_hash):
            raise ValueError("INVALID_RUNTIME_PLAN")
        request_hash = owner_plan.get("request_sha256")
        if not isinstance(request_hash, str) or not SHA.fullmatch(request_hash):
            raise ValueError("INVALID_RUNTIME_REQUEST_HASH")
        result["owner_plan_sha256"] = plan_hash
        result["owner_request_sha256"] = request_hash
        result["budgets"] = request.get("budgets", {})
    else:
        identifier(adapter["proposal_id"])
    if revision:
        result["owner_revision"] = revision
    return result


def build_plan(workflow, config):
    validate_workflow(workflow, config)
    selected = {step["adapter"] for step in workflow["steps"]}
    adapters = {name: bind_adapter(config["adapters"][name]) for name in sorted(selected)}
    catalog = {}
    for skill in config["catalog"]:
        locked = lock_skill(skill)
        if locked["id"] in catalog:
            raise ValueError("DUPLICATE_SKILL")
        catalog[locked["id"]] = locked
    wanted = {sid for step in workflow["steps"] for sid in step["skills"]}
    if not wanted <= catalog.keys():
        raise ValueError("UNKNOWN_SKILL")
    plan = {
        "schema": "quant.workflow_plan.v1",
        "workflow": workflow,
        "adapters": adapters,
        "skills": [catalog[sid] for sid in sorted(wanted)],
    }
    return json.loads(canonical({**plan, "plan_sha256": digest(plan)}))


def verify_bindings(plan):
    body = {k: v for k, v in plan.items() if k != "plan_sha256"}
    if digest(body) != plan["plan_sha256"]:
        raise ValueError("PLAN_HASH_MISMATCH")
    for adapter in plan["adapters"].values():
        for path, expected in adapter["pins"].items():
            if file_sha(path) != expected:
                raise ValueError("OWNER_BINDING_CHANGED")
    for skill in plan["skills"]:
        lock_skill(skill)
