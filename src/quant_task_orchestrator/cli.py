"""Operator entry point. Only explicit mutation commands write state."""

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

from .contracts import build_plan, read_json, verify_bindings
from .owners import OwnerError
from .scheduler import Scheduler
from .store import Store


def _operations_parsers(commands):
    inbox = commands.add_parser("inbox", help="Consume one explicitly configured local inbox batch")
    inbox.add_argument("--inbox", required=True, type=Path)
    inbox.add_argument("--ledger", required=True, type=Path)
    for name in ("outbox-list", "outbox-ack", "outbox-enqueue"):
        command = commands.add_parser(
            name, help="Local notification receipts; no external transport"
        )
        command.add_argument("--ledger", required=True, type=Path)
        if name == "outbox-list":
            command.add_argument("--include-acked", action="store_true")
        elif name == "outbox-ack":
            command.add_argument("notification_id")
        else:
            command.add_argument("workflow_id")
            command.add_argument("--action-signature", required=True)
    skill = commands.add_parser(
        "skill-install", help="Install one exact locked catalog entry as inert text"
    )
    skill.add_argument("--config", required=True, type=Path)
    skill.add_argument("--skill-id", required=True)
    skill.add_argument("--destination", required=True, type=Path)
    release = commands.add_parser(
        "release-stage", help="Stage a verified wheel without installing or activating"
    )
    release.add_argument("--wheel", required=True, type=Path)
    release.add_argument("--sha256", required=True)
    release.add_argument("--revision", required=True)
    release.add_argument("--releases", required=True, type=Path)
    service = commands.add_parser("service-unit", help="Generate a read-only GUI service proposal")
    for name in ("release", "data-root", "config-root"):
        service.add_argument("--" + name, required=True, type=Path)
    service.add_argument("--port", type=int, default=8787)
    service.add_argument("--output", type=Path)
    backup = commands.add_parser("backup", help="Create and integrity-check a new SQLite backup")
    backup.add_argument("--source", required=True, type=Path)
    backup.add_argument("--destination", required=True, type=Path)
    shadow = commands.add_parser(
        "shadow-check", help="Run hash-approved read-only data checks in a new isolated namespace"
    )
    shadow.add_argument("--config", type=Path, required=True)
    shadow.add_argument("--expected-config-sha256", required=True)
    shadow.add_argument("--output-root", type=Path, required=True)
    storage = commands.add_parser(
        "storage-check", help="Read disk availability without deleting files"
    )
    storage.add_argument("--root", type=Path, required=True)
    storage.add_argument("--minimum-free-bytes", type=int, default=1_073_741_824)
    restore = commands.add_parser("restore", help="Verify and restore a backup to a new target")
    restore.add_argument("--source", required=True, type=Path)
    restore.add_argument("--destination", required=True, type=Path)
    restore.add_argument("--sha256", required=True)
    migration = commands.add_parser(
        "migration-check", help="Check ownership without switching schedules"
    )
    migration.add_argument("--input", required=True, type=Path)
    preview = commands.add_parser("outbox-preview", help="Preview a notification without sending")
    preview.add_argument("notification_id")
    preview.add_argument("--ledger", required=True, type=Path)
    health = commands.add_parser(
        "health", help="Verify an explicit loopback read-only workbench health endpoint"
    )
    health.add_argument("--url", required=True)
    health.add_argument("--token-file", type=Path)


def _independent_operation(args):
    from .deployment import backup_database, service_unit, stage_release, verify_health
    from .event_inbox import acknowledge_notification, list_notifications, safe_path

    if args.command == "shadow-check":
        from .shadow import run_shadow

        return run_shadow(args.config, args.expected_config_sha256, args.output_root)
    if args.command == "storage-check":
        from .ops import storage_assessment

        return storage_assessment(args.root, minimum_free_bytes=args.minimum_free_bytes)
    if args.command in {"restore", "migration-check", "outbox-preview"}:
        from .ops import dispatch_notification, restore_database, scheduler_migration_plan

        if args.command == "restore":
            return restore_database(args.source, args.destination, args.sha256)
        if args.command == "outbox-preview":
            return dispatch_notification(args.ledger, args.notification_id)
        from .contracts import exact

        request = read_json(args.input)
        exact(request, {"schema", "old_owner", "new_owner", "old_active", "new_active"})
        if request.pop("schema") != "quant.scheduler_migration_request.v1":
            raise ValueError("INVALID_MIGRATION_REQUEST")
        return scheduler_migration_plan(**request)
    if args.command == "outbox-list":
        return {
            "notifications": list_notifications(args.ledger, include_acked=args.include_acked),
            "transport": "local_outbox",
        }
    if args.command == "outbox-ack":
        return acknowledge_notification(args.ledger, args.notification_id)
    if args.command == "skill-install":
        from .contracts import exact, lock_skill
        from .skill_install import install_skill

        config = read_json(args.config)
        exact(config, {"schema", "adapters", "catalog"})
        if config["schema"] != "quant.orchestrator_config.v1" or not isinstance(
            config["catalog"], list
        ):
            raise ValueError("INVALID_CONFIG")
        matches = [
            entry
            for entry in config["catalog"]
            if isinstance(entry, dict) and entry.get("id") == args.skill_id
        ]
        if len(matches) != 1:
            raise ValueError("EXACT_SKILL_SELECTION_REQUIRED")
        skill = lock_skill(matches[0])
        return install_skill(
            skill["source"],
            skill["revision"],
            skill["path"],
            skill["sha256"],
            args.destination,
            **{
                key: skill[key]
                for key in ("owner_repo", "permissions", "input_contract", "output_contract")
            },
        )
    if args.command == "release-stage":
        return stage_release(args.wheel, args.sha256, args.revision, args.releases)
    if args.command == "service-unit":
        unit = service_unit(args.release, args.data_root, args.config_root, port=args.port)
        if args.output:
            output = safe_path(args.output)
            with output.open("x", encoding="utf-8") as stream:
                stream.write(unit)
            output.chmod(0o600)
        return {"unit": unit, "activated": False}
    if args.command == "backup":
        return backup_database(args.source, args.destination)
    if args.command == "health":
        from .auth import read_token

        return verify_health(
            args.url, token=read_token(args.token_file) if args.token_file else None
        )
    raise ValueError("UNKNOWN_OPERATION")


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
        "--allow-kind",
        action="append",
        choices=(
            "runtime",
            "research",
            "data",
            "report",
            "native_session",
            "raw_observation",
            "research_snapshot",
            "codex_task",
        ),
        required=True,
    )
    approve.add_argument("--operator", required=True)
    for operation in ("inspect", "cancel", "tick", "events"):
        command = commands.add_parser(operation)
        command.add_argument("workflow_id")
        if operation == "events":
            command.add_argument("--after", type=int, default=0)
    listing = commands.add_parser("list")
    listing.add_argument("--limit", type=int, default=100)
    listing.add_argument("--offset", type=int, default=0)
    commands.add_parser("metrics")
    commands.add_parser("capabilities")
    conformance = commands.add_parser("conformance")
    conformance.add_argument("--config", type=Path, required=True)
    recovery = commands.add_parser("recovery")
    recovery.add_argument("workflow_id")
    event = commands.add_parser("event")
    event.add_argument("--file", required=True, type=Path)
    run = commands.add_parser("run")
    run.add_argument("--interval", type=float, default=5)
    run.add_argument("--once", action="store_true")
    run.add_argument("--inbox", type=Path)
    run.add_argument("--ledger", type=Path)
    tui = commands.add_parser("tui")
    tui.add_argument("--once", action="store_true")
    api = commands.add_parser("serve-api")
    api.add_argument("--host", default="127.0.0.1")
    api.add_argument("--port", type=int, default=8787)
    api.add_argument("--token-file", type=Path)
    _operations_parsers(commands)
    args = parser.parse_args(argv)
    try:
        if args.command in {
            "shadow-check",
            "storage-check",
            "restore",
            "migration-check",
            "outbox-preview",
            "outbox-list",
            "outbox-ack",
            "skill-install",
            "release-stage",
            "service-unit",
            "backup",
            "health",
        }:
            result = _independent_operation(args)
        elif args.command == "capabilities":
            from .adapters import adapter_catalog

            result = adapter_catalog()
        elif args.command == "conformance":
            from .contracts import bind_adapter, exact

            config = read_json(args.config)
            exact(config, {"schema", "adapters", "catalog"})
            if config["schema"] != "quant.orchestrator_config.v1":
                raise ValueError("INVALID_CONFIG")
            result = {
                "schema": "quant.adapter_conformance.v1",
                "permission_grant": False,
                "adapters": [],
            }
            for name, adapter in config["adapters"].items():
                bound = bind_adapter(adapter)
                result["adapters"].append(
                    {
                        "id": name,
                        "kind": bound["kind"],
                        "owner_revision": bound.get("owner_revision"),
                        "contract_validated": True,
                        "pin_count": len(bound["pins"]),
                        "fault_injection_tested": False,
                    }
                )
        elif args.command == "plan":
            result = build_plan(read_json(args.workflow), read_json(args.config))
            if args.output:
                # Plans contain private configuration locators. Never overwrite evidence.
                with args.output.open("x", encoding="utf-8") as target:
                    target.write(json.dumps(result, indent=2) + "\n")
                args.output.chmod(0o600)
        else:
            if args.database is None:
                parser.error("--database is required for this command")
            if args.command == "run":
                if not 0.2 <= args.interval <= 3600:
                    raise ValueError("INVALID_POLL_INTERVAL")
                if bool(args.inbox) != bool(args.ledger):
                    raise ValueError("INBOX_AND_LEDGER_REQUIRED_TOGETHER")
            if args.command == "tui":
                from .tui import run as run_tui

                run_tui(args.database, once=args.once)
                return 0
            if args.command == "serve-api":
                from .api import serve

                serve(args.database, args.host, args.port, args.token_file)
                return 0
            readonly = args.command in {
                "inspect",
                "list",
                "events",
                "metrics",
                "recovery",
                "outbox-enqueue",
            }
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
                    result = {
                        "schema": "quant.workflow_list.v1",
                        "workflows": store.list(args.limit, args.offset),
                        "pagination": store.pagination(args.limit, args.offset),
                    }
                elif args.command == "metrics":
                    result = store.metrics()
                elif args.command == "recovery":
                    view = store.view(args.workflow_id)
                    result = {
                        "schema": "quant.workflow_recovery.v1",
                        "workflow_id": args.workflow_id,
                        "steps": [{"id": step["id"], **step["recovery"]} for step in view["steps"]],
                    }
                elif args.command == "events":
                    result = {"events": store.events(args.workflow_id, max(0, args.after))}
                elif args.command == "event":
                    result = store.hint(read_json(args.file))
                elif args.command == "inbox":
                    from .event_inbox import consume_once

                    result = consume_once(store, args.inbox, args.ledger)
                elif args.command == "outbox-enqueue":
                    from .event_inbox import enqueue_notification

                    result = enqueue_notification(
                        args.ledger, store.view(args.workflow_id), args.action_signature
                    )
                elif args.command == "tick":
                    result = Scheduler(store).tick(args.workflow_id)
                else:
                    inbox_result = None
                    while True:
                        if args.inbox:
                            from .event_inbox import consume_once

                            inbox_result = consume_once(store, args.inbox, args.ledger)
                        for workflow_id in store.scheduler_ids():
                            Scheduler(store).tick(workflow_id)
                        if args.once:
                            break
                        time.sleep(args.interval)
                    result = {"workflows": store.list()}
                    if inbox_result is not None:
                        result["inbox"] = inbox_result
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except KeyboardInterrupt:
        return 130
    except sqlite3.Error:
        code = "DATABASE_UNAVAILABLE"
    except OwnerError as exc:
        code = exc.code
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
        code = "OPERATION_REJECTED"
    print(
        json.dumps(
            {"schema": "quant.orchestrator_error.v1", "code": code, "promotion_authorized": False}
        ),
        file=sys.stderr,
    )
    return 1
