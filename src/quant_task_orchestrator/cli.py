"""Operator entry point. Only explicit mutation commands write state."""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

from .contracts import build_plan, read_json, verify_bindings
from .owners import OwnerError
from .scheduler import Scheduler
from .store import Store


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--workflow", required=True, type=Path)
    plan.add_argument("--config", required=True, type=Path)
    plan.add_argument("--output", type=Path)
    submit = commands.add_parser("submit")
    submit.add_argument("--plan", required=True, type=Path)
    approve = commands.add_parser("approve")
    approve.add_argument("workflow_id")
    approve.add_argument("--plan-sha256", required=True)
    approve.add_argument(
        "--allow-kind", action="append", choices=("runtime", "research"), required=True
    )
    approve.add_argument("--operator", required=True)
    for operation in ("inspect", "cancel", "tick", "events"):
        command = commands.add_parser(operation)
        command.add_argument("workflow_id")
        if operation == "events":
            command.add_argument("--after", type=int, default=0)
    commands.add_parser("list")
    event = commands.add_parser("event")
    event.add_argument("--file", required=True, type=Path)
    run = commands.add_parser("run")
    run.add_argument("--interval", type=float, default=5)
    run.add_argument("--once", action="store_true")
    tui = commands.add_parser("tui")
    tui.add_argument("--once", action="store_true")
    api = commands.add_parser("serve-api")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8787)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = build_plan(read_json(args.workflow), read_json(args.config))
            if args.output:
                # Plans contain private configuration locators. Never overwrite evidence.
                with args.output.open("x", encoding="utf-8") as target:
                    target.write(json.dumps(result, indent=2) + "\n")
                args.output.chmod(0o600)
        else:
            if args.database is None:
                parser.error("--database is required for this command")
            if args.command == "tui":
                from .tui import run as run_tui

                run_tui(args.database, once=args.once)
                return 0
            if args.command == "serve-api":
                from .api import serve

                serve(args.database, args.host, args.port)
                return 0
            readonly = args.command in {"inspect", "list", "events"}
            with Store(args.database, readonly=readonly) as store:
                if args.command == "submit":
                    plan = read_json(args.plan)
                    verify_bindings(plan)
                    result = store.submit(plan)
                elif args.command == "approve":
                    result = store.approve(
                        args.workflow_id, args.plan_sha256, args.allow_kind, args.operator
                    )
                elif args.command == "cancel":
                    result = store.cancel(args.workflow_id)
                elif args.command == "inspect":
                    result = store.view(args.workflow_id)
                elif args.command == "list":
                    result = {"schema": "quant.workflow_list.v1", "workflows": store.list()}
                elif args.command == "events":
                    result = {"events": store.events(args.workflow_id, max(0, args.after))}
                elif args.command == "event":
                    result = store.hint(read_json(args.file))
                elif args.command == "tick":
                    result = Scheduler(store).tick(args.workflow_id)
                else:
                    if not 0.2 <= args.interval <= 3600:
                        raise ValueError("INVALID_POLL_INTERVAL")
                    while True:
                        for workflow_id in store.scheduler_ids():
                            Scheduler(store).tick(workflow_id)
                        if args.once:
                            break
                        time.sleep(args.interval)
                    result = {"workflows": store.list()}
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except KeyboardInterrupt:
        return 130
    except sqlite3.Error:
        code = "DATABASE_UNAVAILABLE"
    except OwnerError as exc:
        code = exc.code
    except (ValueError, OSError, KeyError, TypeError, RuntimeError):
        code = "OPERATION_REJECTED"
    print(
        json.dumps(
            {"schema": "quant.orchestrator_error.v1", "code": code, "promotion_authorized": False}
        ),
        file=sys.stderr,
    )
    return 1
