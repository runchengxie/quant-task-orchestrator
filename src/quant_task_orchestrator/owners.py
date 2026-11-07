"""Fixed owner CLI adapters. These supervise trusted CLIs, not untrusted code."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time


class OwnerError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Owner:
    def __init__(self, binding, on_call=None):
        self.binding = binding
        self.on_call = on_call

    def call(self, arguments, *, accepted=(0,)):
        started, success = time.monotonic(), False
        try:
            value = self._call(arguments, accepted=accepted)
            success = True
            return value
        finally:
            if self.on_call:
                self.on_call(success, time.monotonic() - started)

    def _call(self, arguments, *, accepted=(0,)):
        # Bound file-backed capture prevents unbounded Python heap consumption.
        # OS disk quotas remain the operator's responsibility for a misbehaving CLI.
        environment = {
            k: os.environ[k]
            for k in ("PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH", "TMPDIR")
            if k in os.environ
        }
        if self.binding["kind"] == "codex_task":
            # Preserve the CLI's normal authentication location and transport.
            # Values are inherited only; never read credential files or project them.
            for key in (
                "HOME",
                "CODEX_HOME",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "NO_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
                "no_proxy",
            ):
                if key in os.environ:
                    environment[key] = os.environ[key]
        environment["PYTHONNOUSERSITE"] = "1"
        with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
            process = subprocess.Popen(
                [*self.binding["command"], *arguments],
                stdout=out,
                stderr=err,
                env=environment,
                start_new_session=True,
            )
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise OwnerError("OWNER_RESPONSE_UNKNOWN") from None
            if out.tell() > 1_048_576 or err.tell() > 1_048_576:
                raise OwnerError("OWNER_OUTPUT_TOO_LARGE")
            out.seek(0)
            err.seek(0)
            raw = out.read() if process.returncode in accepted else err.read()
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            raise OwnerError("OWNER_INVALID_JSON") from None
        if not isinstance(value, dict):
            raise OwnerError("OWNER_INVALID_OBJECT")
        if process.returncode not in accepted:
            # Never forward owner free text or private paths to the public view.
            code = value.get("code")
            raise OwnerError(
                "JOB_NOT_FOUND" if code == "JOB_NOT_FOUND" else "OWNER_OPERATION_FAILED"
            )
        return value

    def runtime_lookup(self):
        try:
            return self.call(["lookup", "--idempotency-key", self.binding["idempotency_key"]])
        except OwnerError as exc:
            if exc.code == "JOB_NOT_FOUND":
                return None
            raise

    def research_args(self, operation, *extra):
        return [
            "--config",
            self.binding["config"],
            "--expected-config-sha256",
            self.binding["pins"][self.binding["config"]],
            operation,
            *extra,
        ]

    def runtime_submit(self):
        arguments = ["submit"]
        if self.binding["queue"]:
            arguments.append("--queue")
        return self.call(
            [
                *arguments,
                self.binding["request"],
                "--expected-plan-sha256",
                self.binding["owner_plan_sha256"],
            ]
        )

    def confirm_existing(self, receipt):
        # A proven existing key permits an idempotent replay to ask the owner to
        # check its request fingerprint. Never replay when lookup finds no job.
        confirmed = self.runtime_submit()
        if confirmed.get("job_id") != receipt.get("job_id"):
            raise OwnerError("OWNER_IDENTITY_MISMATCH")
        return receipt

    def start(self):
        if self.binding["kind"] == "research_snapshot":
            from .research_snapshot import observe

            return observe(self.binding, self)

        if self.binding["kind"] == "raw_observation":
            from .raw_owner import observe

            return observe(self.binding, self)
        if self.binding["kind"] == "codex_task":
            from .codex_owner import dispatch

            return dispatch(self.binding, "start", self)
        if self.binding["kind"] in {"data", "report"}:
            from .asset_owners import start_asset

            return start_asset(self.binding, self)
        if self.binding["kind"] == "native_session":
            from .native_owner import start_native

            return start_native(self.binding, self)
        if self.binding["kind"] == "runtime":
            existing = self.runtime_lookup()
            return (
                self.confirm_existing(existing) if existing is not None else self.runtime_submit()
            )
        return self.call(
            self.research_args("advance", self.binding["proposal_id"]), accepted=(0, 1)
        )

    def inspect(self, owner_id):
        if self.binding["kind"] == "research_snapshot":
            from .research_snapshot import observe

            return observe(self.binding, self)

        if self.binding["kind"] == "codex_task":
            from .codex_owner import dispatch

            return dispatch(self.binding, "inspect", self)
        if self.binding["kind"] == "raw_observation":
            receipt = self.start()
            if owner_id is not None and self.identity(receipt) != owner_id:
                raise OwnerError("OWNER_IDENTITY_MISMATCH")
            return receipt
        if self.binding["kind"] in {"data", "report", "native_session"}:
            receipt = self.start()
            if owner_id is not None and self.identity(receipt) != owner_id:
                raise OwnerError("OWNER_IDENTITY_MISMATCH")
            return receipt
        if self.binding["kind"] == "runtime":
            receipt = (
                self.runtime_lookup() if owner_id is None else self.call(["inspect", owner_id])
            )
            if receipt is None:
                raise OwnerError("SUBMISSION_UNCERTAIN_NO_RECEIPT")
            if owner_id is not None and receipt.get("job_id") != owner_id:
                raise OwnerError("OWNER_IDENTITY_MISMATCH")
            return self.confirm_existing(receipt) if owner_id is None else receipt
        # advance only reconciles an already bound proposal; no admission or
        # compute reservation is repeated by the Research owner.
        return self.call(
            self.research_args("advance", self.binding["proposal_id"]), accepted=(0, 1)
        )

    def cancel(self, owner_id):
        if self.binding["kind"] == "research_snapshot":
            from .research_snapshot import observe

            return observe(self.binding, self)

        if self.binding["kind"] == "codex_task":
            from .codex_owner import dispatch

            return dispatch(self.binding, "cancel", self)
        if self.binding["kind"] == "raw_observation":
            return self.inspect(owner_id)
        if self.binding["kind"] in {"data", "report", "native_session"}:
            return self.inspect(owner_id)
        if self.binding["kind"] == "research":
            receipt = self.inspect(owner_id)
            if receipt.get("state") in {"SUPPORTED", "DISCARDED", "DIAGNOSTIC_COMPLETED"}:
                return receipt
            raise OwnerError("OWNER_CANCELLATION_REQUIRES_OPERATOR")
        if owner_id is None:
            owner_id = self.inspect(None)["job_id"]
        return self.call(["cancel", owner_id])

    def identity(self, receipt):
        if self.binding["kind"] in {"raw_observation", "codex_task", "research_snapshot"}:
            return self.grade(receipt)[1]
        if self.binding["kind"] in {"data", "report"}:
            from .asset_owners import grade_asset

            return grade_asset(self.binding, receipt)[1]
        if self.binding["kind"] == "native_session":
            from .native_owner import grade_native

            return grade_native(self.binding, receipt)[1]
        identity = receipt.get("job_id" if self.binding["kind"] == "runtime" else "proposal_id")
        if self.binding["kind"] == "research" and identity != self.binding["proposal_id"]:
            raise OwnerError("OWNER_IDENTITY_MISMATCH")
        return identity

    def evidence(self, receipt):
        if self.binding["kind"] == "research_snapshot":
            from .research_snapshot import evidence_snapshot

            return evidence_snapshot(self.binding, receipt)

        if self.binding["kind"] == "raw_observation":
            from .raw_owner import evidence_raw

            return evidence_raw(self.binding, receipt)
        if self.binding["kind"] in {"data", "report"}:
            from .asset_owners import evidence_asset

            return evidence_asset(self.binding, receipt)
        if self.binding["kind"] == "runtime":
            return (
                {
                    "input_integrity": {
                        "status": "verified",
                        "source": "quant-backtest-runtime",
                        "evidence_sha256": self.binding["owner_request_sha256"],
                    }
                }
                if receipt.get("status") == "SUCCEEDED"
                else {}
            )
        return {}

    def execution(self, receipt):
        if self.binding["kind"] == "codex_task":
            from .codex_owner import execution_codex

            return execution_codex(self.binding, receipt)
        return None

    def grade(self, receipt):
        if self.binding["kind"] == "research_snapshot":
            from .research_snapshot import grade_snapshot

            return grade_snapshot(self.binding, receipt)

        if self.binding["kind"] == "raw_observation":
            from .raw_owner import grade_raw

            return grade_raw(self.binding, receipt)
        if self.binding["kind"] == "codex_task":
            from .codex_owner import grade_codex

            return grade_codex(self.binding, receipt)
        if self.binding["kind"] in {"data", "report"}:
            from .asset_owners import grade_asset

            return grade_asset(self.binding, receipt)
        if self.binding["kind"] == "native_session":
            from .native_owner import grade_native

            return grade_native(self.binding, receipt)
        if self.binding["kind"] == "runtime":
            owner_id, state = receipt.get("job_id"), receipt.get("status")
            if not isinstance(owner_id, str) or not owner_id:
                raise OwnerError("OWNER_IDENTITY_MISMATCH")
            if state == "SUCCEEDED":
                result = self.call(["result", owner_id])
                if (
                    result.get("job_id") != owner_id
                    or result.get("request_sha256") != self.binding["owner_request_sha256"]
                ):
                    raise OwnerError("OWNER_IDENTITY_MISMATCH")
                return "SUCCEEDED", owner_id, "RESULT_INTEGRITY_VERIFIED"
            if state in {"FAILED", "CANCELLED"}:
                return state, owner_id, "NOT_VERIFIED"
            if state in {"SUBMITTED", "RUNNING", "QUEUED"}:
                return "RUNNING", owner_id, "NOT_VERIFIED"
            raise OwnerError("UNKNOWN_OWNER_STATE")
        owner_id, state = receipt.get("proposal_id"), receipt.get("state")
        if owner_id != self.binding["proposal_id"]:
            raise OwnerError("OWNER_IDENTITY_MISMATCH")
        if state in {"SUPPORTED", "DISCARDED", "DIAGNOSTIC_COMPLETED"}:
            return "SUCCEEDED", owner_id, state
        if state in {"BLOCKED", "REJECTED", "REQUIRES_HUMAN_REVIEW", "COMPLETED_UNVERIFIED"}:
            return "BLOCKED", owner_id, state
        if state in {"SUBMITTED", "SUBMIT_UNKNOWN", "ADMITTED"}:
            return "RUNNING", owner_id, state
        raise OwnerError("UNKNOWN_OWNER_STATE")
