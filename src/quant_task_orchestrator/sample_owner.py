"""Public synthetic Runtime protocol peer; no market engine or network access."""

import hashlib
import json
import sys
from pathlib import Path


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args.pop(0)).resolve()
    operation = args.pop(0)
    root.mkdir(parents=True, exist_ok=True)
    if operation in {"plan", "submit"}:
        args = [arg for arg in args if arg != "--queue"]
        request = json.loads(Path(args[0]).read_text())
        request_hash = fingerprint(request)
        plan_hash = fingerprint({"synthetic": True, "request_sha256": request_hash})
        if operation == "plan":
            result = {"request_sha256": request_hash, "plan_sha256": plan_hash}
        else:
            if args[1:] != ["--expected-plan-sha256", plan_hash]:
                raise ValueError("PLAN_HASH_MISMATCH")
            job_id = "synthetic-" + request_hash[:24]
            result = {
                "job_id": job_id,
                "status": "SUCCEEDED",
                "request_sha256": request_hash,
                "synthetic": True,
                "metrics": request["synthetic_metrics"],
            }
            destination = root / (job_id + ".json")
            if destination.exists() and json.loads(destination.read_text()) != result:
                raise ValueError("IDEMPOTENCY_CONFLICT")
            destination.write_text(json.dumps(result))
            (root / (request["idempotency_key"] + ".key")).write_text(job_id)
    elif operation == "lookup":
        key_path = root / (args[1] + ".key")
        if not key_path.exists():
            print(json.dumps({"code": "JOB_NOT_FOUND"}), file=sys.stderr)
            return 1
        result = json.loads((root / (key_path.read_text() + ".json")).read_text())
    elif operation in {"inspect", "result"}:
        result = json.loads((root / (args[0] + ".json")).read_text())
    else:
        raise ValueError("UNSUPPORTED_SYNTHETIC_OPERATION")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
