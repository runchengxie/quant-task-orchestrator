"""Synthetic owner peer for process-level coordinator contract checks."""

import hashlib
import json
import sys
from pathlib import Path

state_path = Path(sys.argv[1])
args = sys.argv[2:]
config_path = Path(args[args.index("--config") + 1])
config = json.loads(config_path.read_text())
plan = hashlib.sha256(
    json.dumps(config, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
operation = next(a for a in args if a in {"plan", "start", "inspect", "resume", "cancel"})
if operation == "plan":
    print(
        json.dumps(
            {
                "plan_sha256": plan,
                "config_sha256": plan,
                "config": config,
                "tool_policy": "research-read-only"
                if config["schema"] == "research.codex-task/v2"
                else "tool-free-read-only",
                "tool_profile_sha256": config.get("tool_profile_sha256"),
                "tool_call_limit_per_turn": 32
                if config["schema"] == "research.codex-task/v2"
                else 0,
                "side_effect_scope": "tool-free-read-only; local journal/events/session persistence only",
            }
        )
    )
    raise SystemExit()
key = args[args.index("--key") + 1]
state = json.loads(state_path.read_text())
state.setdefault("_operations", []).append(operation)
if operation in {"start", "resume"}:
    assert args[args.index("--expected-plan-sha256") + 1] == plan
    if operation == "resume":
        assert args[args.index("--session") + 1] == state["session"]
        assert args[args.index("--receipt") + 1] == state["receipt"]
        turn = state["turn"] + 1
        session = state["session"]
    else:
        turn, session = 1, None
    state.update(owner_id=key, plan_sha256=plan, status="admitted", turn=turn, session=session)
elif operation == "cancel":
    state["status"] = "cancel_requested"
else:
    output = Path(config["output_directory"])
    output.mkdir(exist_ok=True)
    turn = state["turn"]
    events = output / f"turn-{turn}.events.jsonl"
    events.write_text("{}\n")
    cancelled = state["status"] == "cancel_requested"
    state.update(
        schema="research.codex-task-receipt/v1",
        owner_id=key,
        plan_sha256=plan,
        status="cancelled" if cancelled else "completed",
        turn=turn,
        session="00000000-0000-4000-8000-000000000001",
        observed_tokens=None if cancelled else 12,
        cumulative_tokens=None if cancelled else turn * 12,
        cumulative_wall_seconds=0.25,
        usage=None
        if cancelled
        else {
            "input_tokens": 10,
            "output_tokens": 2,
            "cached_input_tokens": 0,
            "reasoning_output_tokens": None,
        },
        config_sha256=plan,
        executable_sha256=config["executable_sha256"],
        events_sha256=hashlib.sha256(events.read_bytes()).hexdigest(),
    )
    path = output / f"turn-{turn}.json"
    path.write_text(json.dumps(state))
    state["receipt"] = str(path)
    state["receipt_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
state_path.write_text(json.dumps(state))
print(json.dumps(state))
