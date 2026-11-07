"""Coordinator-observed durations, explicitly distinct from CPU/model accounting."""

from datetime import UTC, datetime

STATE_FIELDS = {
    "WAITING": "waiting_seconds",
    "DISPATCHING": "unknown_seconds",
    "RUNNING": "running_seconds",
    "BLOCKED": "blocked_seconds",
    "UNKNOWN": "unknown_seconds",
}


def elapsed(start, finish):
    try:
        a, b = datetime.fromisoformat(start), datetime.fromisoformat(finish)
        if a.tzinfo is None or b.tzinfo is None:
            return 0.0
        return max(0.0, (b - a).total_seconds())
    except (ValueError, TypeError):
        return 0.0


def step_metrics(transitions, telemetry=None):
    result = {name: 0.0 for name in set(STATE_FIELDS.values())}
    result.update(
        {
            "coverage": "since_observation_start" if transitions else "unavailable",
            "owner_calls": 0,
            "owner_errors": 0,
            "owner_call_wall_seconds": 0.0,
            "model_cost_usd": None,
            "cpu_seconds": None,
        }
    )
    end = datetime.now(UTC).isoformat()
    for index, transition in enumerate(transitions):
        field = STATE_FIELDS.get(transition["status"])
        if field:
            finish = transitions[index + 1]["created"] if index + 1 < len(transitions) else end
            result[field] += elapsed(transition["created"], finish)
    if telemetry:
        result.update(
            {
                key: telemetry[key]
                for key in ("owner_calls", "owner_errors", "owner_call_wall_seconds")
            }
        )
    for name in set(STATE_FIELDS.values()):
        result[name] = round(result[name], 6)
    return result
