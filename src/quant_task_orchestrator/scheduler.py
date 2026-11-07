"""Single coordinator, durable dispatch intent, conservative reconciliation."""

import fcntl
from contextlib import contextmanager

from .contracts import verify_bindings
from .owners import Owner, OwnerError
from .store import TERMINAL


class Scheduler:
    def __init__(self, store):
        self.store = store

    @contextmanager
    def lock(self):
        with self.store.path.with_suffix(".scheduler.lock").open("a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise RuntimeError("SCHEDULER_ALREADY_RUNNING") from None
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def tick(self, wid):
        with self.lock():
            row, plan = self.store.record(wid), self.store.plan(wid)
            if not row["approval"]:
                if row["cancelled"]:
                    for step in self.store.steps(wid):
                        self.store.set_step(wid, step["id"], "CANCELLED")
                return self.store.view(wid)
            steps = {step["id"]: step for step in self.store.steps(wid)}
            for definition in plan["workflow"]["steps"]:
                sid = definition["id"]
                step = steps[sid]
                if step["status"] in TERMINAL:
                    continue
                current_steps = {item["id"]: item for item in self.store.steps(wid)}
                if not self.store.record(wid)["cancelled"] and any(
                    current_steps[dep]["status"] in {"FAILED", "CANCELLED"}
                    or current_steps[dep]["error"] == "DEPENDENCY_UNAVAILABLE"
                    for dep in definition["depends_on"]
                ):
                    self.store.set_step(wid, sid, "BLOCKED", error="DEPENDENCY_UNAVAILABLE")
                    continue
                try:
                    verify_bindings(plan)
                except (ValueError, OSError):
                    self.store.set_step(wid, sid, "BLOCKED", error="OWNER_BINDING_CHANGED")
                    continue
                owner = Owner(plan["adapters"][definition["adapter"]])
                # Cancellation is read again immediately before each potential dispatch.
                cancelled = self.store.record(wid)["cancelled"]
                try:
                    if cancelled:
                        if step["status"] == "WAITING":
                            self.store.set_step(wid, sid, "CANCELLED")
                            continue
                        receipt = owner.cancel(step["owner_id"])
                    elif step["status"] in {"DISPATCHING", "UNKNOWN", "RUNNING", "BLOCKED"}:
                        receipt = owner.inspect(step["owner_id"])
                    elif all(
                        current_steps[dep]["status"] == "SUCCEEDED"
                        for dep in definition["depends_on"]
                    ):
                        self.store.set_step(wid, sid, "DISPATCHING")
                        receipt = owner.start()
                    else:
                        continue
                    # Persist the identity before asking the owner to verify result files.
                    identity = receipt.get(
                        "job_id" if owner.binding["kind"] == "runtime" else "proposal_id"
                    )
                    if not isinstance(identity, str) or not identity:
                        raise OwnerError("OWNER_IDENTITY_MISMATCH")
                    self.store.set_step(wid, sid, "RUNNING", owner_id=identity)
                    status, owner_id, evidence = owner.grade(receipt)
                    self.store.set_step(wid, sid, status, owner_id, evidence)
                except (OwnerError, OSError, ValueError) as exc:
                    code = (
                        exc.code if isinstance(exc, OwnerError) else "OWNER_OPERATION_UNAVAILABLE"
                    )
                    self.store.set_step(wid, sid, "UNKNOWN", error=code)
            return self.store.view(wid)
