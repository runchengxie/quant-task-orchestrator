"""Read immutable Research tool exports without projecting their private contents."""

from pathlib import Path

from .contracts import SHA, exact, file_sha, identifier, read_json


def observe(binding, caller=None):
    from .owners import Owner

    for path, expected in binding["pins"].items():
        if file_sha(path) != expected:
            raise ValueError("OWNER_BINDING_CHANGED")
    receipt = (caller or Owner(binding)).call(
        [
            "--profile",
            binding["profile"],
            "--expected-profile-sha256",
            binding["expected_profile_sha256"],
            "--handle",
            binding["handle"],
        ]
    )
    return validate(binding, receipt)


def validate(binding, receipt):
    if (
        receipt.get("schema") != "research.tool-response/v1"
        or receipt.get("profile_sha256") != binding["expected_profile_sha256"]
        or receipt.get("handle") != binding["handle"]
        or receipt.get("kind") != binding["resource_kind"]
        or receipt.get("content_sha256") != binding["content_sha256"]
        or receipt.get("snapshot") is not True
    ):
        raise ValueError("INVALID_RESEARCH_SNAPSHOT")
    return receipt


def bind_snapshot(adapter):
    exact(adapter, {"kind", "command", "profile", "expected_profile_sha256", "handle"})
    identifier(adapter["handle"])
    command = adapter["command"]
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(x, str) and x for x in command)
    ):
        raise ValueError("INVALID_OWNER_COMMAND")
    paths = [command[0], adapter["profile"], *[x for x in command[1:] if x.endswith(".py")]]
    if not all(Path(path).is_absolute() and Path(path).is_file() for path in paths):
        raise ValueError("ABSOLUTE_OWNER_INPUT_REQUIRED")
    if file_sha(adapter["profile"]) != adapter["expected_profile_sha256"]:
        raise ValueError("PROFILE_HASH_MISMATCH")
    profile = read_json(adapter["profile"])
    if (
        not isinstance(profile, dict)
        or profile.get("schema") != "research.tool-profile/v1"
        or not isinstance(profile.get("resources"), dict)
    ):
        raise ValueError("INVALID_RESEARCH_PROFILE")
    resource = profile["resources"][adapter["handle"]]
    if (
        not isinstance(resource, dict)
        or resource.get("kind") not in {"evidence", "plan", "runtime_status", "artifact"}
        or not isinstance(resource.get("sha256"), str)
        or not SHA.fullmatch(resource["sha256"])
    ):
        raise ValueError("INVALID_RESEARCH_RESOURCE")
    binding = {
        **adapter,
        "pins": {path: file_sha(path) for path in paths},
        "resource_kind": resource["kind"],
        "content_sha256": resource["sha256"],
    }
    observe(binding)
    return binding


def grade_snapshot(binding, receipt):
    validate(binding, receipt)
    return "SUCCEEDED", binding["content_sha256"], "RESEARCH_SNAPSHOT_VERIFIED"


def evidence_snapshot(binding, receipt):
    validate(binding, receipt)
    return {
        "input_integrity": {
            "status": "verified",
            "source": "quant-research",
            "evidence_sha256": binding["content_sha256"],
        }
    }
