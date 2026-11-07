"""Synthetic CLI protocol peer; never used in production adapters."""

import hashlib
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
args = sys.argv[2:]
state = json.loads(path.read_text())
job = "00000000-0000-4000-8000-000000000001"
if args[0] == "plan":
    print(
        json.dumps(
            {
                "plan_sha256": hashlib.sha256(Path(args[1]).read_bytes()).hexdigest(),
                "request_sha256": hashlib.sha256(Path(args[1]).read_bytes()).hexdigest(),
            }
        )
    )
    sys.exit()
if args[0] == "--config":
    assert args[2] == "--expected-config-sha256"
    assert args[3] == hashlib.sha256(Path(args[1]).read_bytes()).hexdigest()
    if args[4] == "advance":
        state["advances"] = state.get("advances", 0) + 1
        path.write_text(json.dumps(state))
        assert args[5] == "proposal-1"
        print(
            json.dumps(
                {
                    "proposal_id": "proposal-1",
                    "state": "SUBMITTED"
                    if state.get("research_pending") and state.get("advances", 0) < 2
                    else "DIAGNOSTIC_COMPLETED",
                }
            )
        )
    elif args[4] == "report":
        print(
            json.dumps(
                {
                    "proposals": [
                        {
                            "proposal_id": "proposal-1",
                            "state": "SUBMITTED"
                            if state.get("research_pending") and state.get("advances", 0) < 2
                            else "DIAGNOSTIC_COMPLETED",
                        }
                    ]
                }
            )
        )
    else:
        raise AssertionError("Unexpected research operation")
    sys.exit()
if args[0] == "lookup" and not state["submissions"]:
    print(json.dumps({"code": "JOB_NOT_FOUND"}), file=sys.stderr)
    sys.exit(1)
if args[0] == "submit":
    assert "--expected-plan-sha256" in args
    if state.get("conflicting_request"):
        print(json.dumps({"code": "IDEMPOTENCY_CONFLICT"}), file=sys.stderr)
        sys.exit(1)
    state["submissions"] = 1
    request_path = args[args.index("--queue") + 1] if "--queue" in args else args[1]
    state["request_sha256"] = hashlib.sha256(Path(request_path).read_bytes()).hexdigest()
    path.write_text(json.dumps(state))
    if state.pop("lose_response", False):
        path.write_text(json.dumps(state))
        sys.exit(1)
if args[0] == "result":
    if state.get("bad_result"):
        print(json.dumps({"code": "RESULT_INTEGRITY_ERROR"}), file=sys.stderr)
        sys.exit(1)
    print(
        json.dumps(
            {
                "job_id": "wrong" if state.get("wrong_identity") else job,
                "request_sha256": "0" * 64
                if state.get("wrong_request_hash")
                else state.get(
                    "request_sha256",
                    hashlib.sha256((path.parent / "request.json").read_bytes()).hexdigest(),
                ),
            }
        )
    )
    sys.exit()
if args[0] == "cancel":
    state["status"] = "CANCELLED"
    path.write_text(json.dumps(state))
print(json.dumps({"job_id": job, "status": state["status"]}))
