"""Stable operator action codes. Actions are advice, never new authority."""


def recovery_for(status, error, kind, evidence, approved):
    actions = []
    requires_operator = False
    code = error or evidence or status
    if status == "WAITING":
        actions = ["wait_for_dependencies"] if approved else ["approve_exact_plan"]
        requires_operator = not approved
    elif error == "OWNER_BINDING_CHANGED":
        actions = ["restore_approved_binding", "inspect_owner"]
        requires_operator = True
    elif error == "EVIDENCE_REQUIREMENTS_UNMET":
        actions = ["owner_review", "collect_pit_evidence"]
        requires_operator = True
    elif error == "DEPENDENCY_UNAVAILABLE":
        actions = ["inspect_dependencies"]
        requires_operator = True
    elif error == "OWNER_CANCELLATION_REQUIRES_OPERATOR":
        actions = ["operator_cancel", "inspect_owner"]
        requires_operator = True
    elif status in {"UNKNOWN", "DISPATCHING"}:
        actions = (
            ["lookup_original_key", "inspect_owner"]
            if kind == "runtime"
            else ["inspect_owner", "verify_original_session"]
            if kind == "native_session"
            else ["inspect_owner"]
        )
        requires_operator = True
    elif status == "BLOCKED":
        actions = ["owner_review"] if kind in {"research", "native_session"} else ["inspect_owner"]
        if evidence in {"PIT_MISSING", "OWNER_ASSESSMENT_BLOCKED"}:
            actions.append("collect_pit_evidence")
        requires_operator = True
    elif status == "RUNNING":
        actions = ["wait_for_owner"]
    elif status == "FAILED":
        actions, requires_operator = ["inspect_owner", "review_new_execution_scope"], True
    elif status == "CANCELLED":
        actions = ["preserve_evidence"]
    return {
        "schema": "quant.recovery_advice.v1",
        "code": code,
        "actions": actions,
        "requires_operator": requires_operator,
        "authorizes_execution": False,
    }
