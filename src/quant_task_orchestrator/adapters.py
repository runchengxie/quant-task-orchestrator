"""Explicit adapter registry. Discovery never expands execution authority."""

ADAPTERS = {
    "runtime": {
        "owner": "quant-backtest-runtime",
        "contract": "quant.backtest_plan.v1",
        "effects": ["job_submit", "job_cancel", "verified_result_read"],
    },
    "research": {
        "owner": "quant-research",
        "contract": "quant.research_campaign_context.v1",
        "effects": ["reconcile_existing_proposal"],
    },
    "data": {
        "owner": "quant-market-data-platform",
        "contract": "quant.data_assessment.v1",
        "effects": [],
    },
    "report": {"owner": "quant-intel-platform", "contract": "quant.market_brief.v1", "effects": []},
    "native_session": {
        "owner": "quant-research",
        "contract": "quant.native_research_session_inspection.v1",
        "effects": [],
    },
}


def adapter_catalog():
    return {
        "schema": "quant.adapter_catalog.v1",
        "permission_grant": False,
        "adapters": [{"kind": kind, **metadata} for kind, metadata in ADAPTERS.items()],
    }
