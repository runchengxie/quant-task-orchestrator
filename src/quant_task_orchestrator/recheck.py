"""Query recorded requirement applicability without refreshing or running Owners."""

from .evidence_scope import assess_check


def recheck_workflow(store, workflow_id):
    view = store.view(workflow_id)
    steps = {step["id"]: step for step in view["steps"]}
    blockers = []
    checked = 0
    for step in view["steps"]:
        for upstream, dimensions in step["requires_evidence"].items():
            for dimension in dimensions:
                checked += 1
                check = steps[upstream]["evidence"]["checks"].get(dimension, {})
                assessment = assess_check(check, step["evidence_context"], dimension=dimension)
                if not assessment["usable"]:
                    blockers.append(
                        {
                            "step_id": step["id"],
                            "upstream_step_id": upstream,
                            "dimension": dimension,
                            "source": check.get("source", "unknown"),
                            "status": check.get("status", "unknown"),
                            "applicability_code": assessment["code"],
                        }
                    )
    return {
        "schema": "quant.workflow_recheck.v1",
        "workflow_id": workflow_id,
        "plan_sha256": view["plan_sha256"],
        "requirements_checked": checked,
        "requirements_met": not blockers,
        "blockers": blockers,
        "observation_scope": "recorded_cache_only",
        "owner_refresh_performed": False,
        "new_plan_required": view["status"] in {"BLOCKED", "FAILED", "NEEDS_RECONCILIATION"},
        "approval_required": True,
        "execution_authorized": False,
        "research_validated": False,
        "promotion_authorized": False,
    }
