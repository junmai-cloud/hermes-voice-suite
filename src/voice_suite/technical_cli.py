"""Command-line entry points for Hermes technical operations.

The CLI is intentionally usable by Hermes over a subprocess boundary: normal
output can be JSON, and no audio, transcript, or secret is accepted by the
ledger commands.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from .codex_worker import CodexCliWorker, CodexWorkerHTTPServer, RemoteCodexWorker
from .technical_ledger import TechnicalLedger
from .technical_ops import (
    AuditPacket,
    OperationKind,
    TaskState,
    WorkerRole,
)
from .technical_service import TechnicalOrchestrator, WorkerPool


def _emit(value: Any, *, as_json: bool = False) -> None:
    if as_json or isinstance(value, (dict, list)):
        print(json.dumps(value, ensure_ascii=False, indent=None if as_json else 2))
    else:
        print(value)


def _ledger(args: argparse.Namespace) -> TechnicalLedger:
    return TechnicalLedger(args.ledger or os.environ.get("VOICE_TECH_LEDGER_PATH"))


def _worker_from_config(
    worker_id: str,
    *,
    role: WorkerRole,
    url_name: str,
    default_repo: str | None = None,
):
    url = os.environ.get(url_name, "").strip()
    token = os.environ.get("CODEX_WORKER_TOKEN", "").strip()
    if url:
        if not token:
            raise SystemExit(f"{url_name} is set but CODEX_WORKER_TOKEN is empty")
        return RemoteCodexWorker(worker_id, url, token, role=role)
    return CodexCliWorker(
        worker_id,
        role=role,
        command=os.environ.get("CODEX_COMMAND", "codex"),
        sandbox=os.environ.get("CODEX_SANDBOX", "workspace-write"),
        default_repo=default_repo or os.environ.get("CODEX_REPO_PATH"),
    )


def _orchestrator(ledger: TechnicalLedger) -> TechnicalOrchestrator:
    vps = _worker_from_config("vps-codex", role=WorkerRole.IMPLEMENTER, url_name="CODEX_VPS_WORKER_URL")
    local = None
    local_url = os.environ.get("CODEX_LOCAL_WORKER_URL", "").strip()
    if local_url:
        local = _worker_from_config(
            "local-codex",
            role=WorkerRole.IMPLEMENTER,
            url_name="CODEX_LOCAL_WORKER_URL",
        )
    else:
        try:
            local_slots = max(0, int(os.environ.get("CODEX_LOCAL_WORKER_SLOTS", "1")))
        except ValueError as exc:
            raise SystemExit("CODEX_LOCAL_WORKER_SLOTS must be an integer") from exc
        if local_slots:
            workers = [
                _worker_from_config(
                    f"local-codex-{index + 1}",
                    role=WorkerRole.IMPLEMENTER,
                    url_name="__CODEX_LOCAL_DISABLED__",
                )
                for index in range(local_slots)
            ]
            local = workers[0] if len(workers) == 1 else WorkerPool(workers, pool_id="local-codex-burst")
    audit_url = os.environ.get("CODEX_AUDITOR_URL", "").strip()
    vps_url = os.environ.get("CODEX_VPS_WORKER_URL", "").strip()
    if audit_url:
        token = os.environ.get("CODEX_WORKER_TOKEN", "").strip()
        if not token:
            raise SystemExit("CODEX_AUDITOR_URL is set but CODEX_WORKER_TOKEN is empty")
        auditor = RemoteCodexWorker("vps-codex-auditor", audit_url, token, role=WorkerRole.AUDITOR)
    elif vps_url:
        raise SystemExit("CODEX_AUDITOR_URL is required when CODEX_VPS_WORKER_URL is remote")
    else:
        auditor = CodexCliWorker(
            "vps-codex-auditor",
            role=WorkerRole.AUDITOR,
            command=os.environ.get("CODEX_COMMAND", "codex"),
            sandbox=os.environ.get("CODEX_SANDBOX", "workspace-write"),
            default_repo=os.environ.get("CODEX_REPO_PATH"),
        )
    return TechnicalOrchestrator(ledger, vps_worker=vps, local_worker=local, auditor_worker=auditor)


def _read_json(value: str | None, filename: str | None) -> dict[str, Any]:
    if value:
        raw = value
    elif filename:
        raw = Path(filename).read_text(encoding="utf-8")
    else:
        raw = sys.stdin.read()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("JSON input must be an object")
    return payload


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", dest="as_json", help="print machine-readable JSON")


def _create(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    orchestrator = _orchestrator(ledger)
    task = orchestrator.register(
        args.summary,
        args.operation,
        args.repo,
        branch=args.branch,
        rollback_plan=args.rollback,
    )
    _emit(task.to_dict(), as_json=True)
    return 0


def _list(args: argparse.Namespace) -> int:
    records = _ledger(args).list(state=args.state)
    _emit(records, as_json=args.as_json)
    return 0


def _show(args: argparse.Namespace) -> int:
    record = _ledger(args).get(args.task_id)
    if record is None:
        raise SystemExit(f"unknown technical task: {args.task_id}")
    _emit(record, as_json=True)
    return 0


def _dispatch(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    orchestrator = _orchestrator(ledger)
    if args.confirm:
        orchestrator.confirm(args.task_id)
    result = orchestrator.dispatch(args.task_id, args.prompt, prefer_local=not args.no_local)
    _emit(result.__dict__, as_json=True)
    return 0


def _submit_audit(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    packet = AuditPacket(
        task_id=args.task_id,
        command=args.command,
        expected=args.expected,
        actual=args.actual,
        exit_code=args.exit_code,
        changed_files=tuple(args.changed_file),
        tests=tuple(args.test),
        health=tuple(args.health),
        next_action=args.next_action,
    )
    prompt = args.prompt
    result = _orchestrator(ledger).submit_audit(args.task_id, packet, prompt)
    _emit(result.__dict__, as_json=True)
    return 0


def _audit(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    payload = args.result_json
    if args.result_file:
        payload = Path(args.result_file).read_text(encoding="utf-8")
    if payload is None:
        payload = sys.stdin.read()
    verdict = _orchestrator(ledger).complete_audit(args.task_id, payload)
    response = verdict.to_dict()
    response["voice_message"] = verdict.voice_summary()
    _emit(response, as_json=True)
    return 0


def _complete(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    orchestrator = _orchestrator(ledger)
    orchestrator.mark_deployed(args.task_id)
    _emit({"task_id": args.task_id, "state": "DEPLOYED"}, as_json=True)
    return 0


def _confirm(args: argparse.Namespace) -> int:
    ledger = _ledger(args)
    _orchestrator(ledger).confirm(args.task_id)
    _emit({"task_id": args.task_id, "user_confirmed": True}, as_json=True)
    return 0


def _worker(args: argparse.Namespace) -> int:
    worker = CodexCliWorker(
        args.worker_id,
        role=args.role,
        command=args.command,
        sandbox=args.sandbox,
        default_repo=args.repo,
    )
    server = CodexWorkerHTTPServer(worker, args.host, args.port, args.token)
    print(json.dumps({"worker_id": args.worker_id, "host": args.host, "port": server.server.server_port}))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.shutdown()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="voice-suite tech")
    parser.add_argument("--ledger", help="SQLite ledger path; defaults to VOICE_TECH_LEDGER_PATH")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="register a logical technical task")
    create.add_argument("--summary", required=True)
    create.add_argument("--operation", required=True, choices=[item.value for item in OperationKind])
    create.add_argument("--repo", required=True)
    create.add_argument("--branch")
    create.add_argument("--rollback", default="Revert the task branch before deployment.")
    create.set_defaults(handler=_create)

    listing = subparsers.add_parser("list", help="list tasks")
    listing.add_argument("--state", type=TaskState, choices=list(TaskState))
    _add_output_options(listing)
    listing.set_defaults(handler=_list)

    show = subparsers.add_parser("show", help="show one task")
    show.add_argument("task_id")
    show.set_defaults(handler=_show)

    dispatch = subparsers.add_parser("dispatch", help="send implementation to local Codex or VPS fallback")
    dispatch.add_argument("task_id")
    dispatch.add_argument("--prompt", required=True)
    dispatch.add_argument("--no-local", action="store_true")
    dispatch.add_argument("--confirm", action="store_true", help="record explicit user confirmation before dispatch")
    dispatch.set_defaults(handler=_dispatch)

    submit = subparsers.add_parser("submit-audit", help="record evidence and send it to VPS Codex")
    submit.add_argument("task_id")
    submit.add_argument("--command", required=True)
    submit.add_argument("--expected", required=True)
    submit.add_argument("--actual", required=True)
    submit.add_argument("--exit-code", type=int)
    submit.add_argument("--changed-file", action="append", default=[])
    submit.add_argument("--test", action="append", default=[])
    submit.add_argument("--health", action="append", default=[])
    submit.add_argument("--next-action", default="")
    submit.add_argument("--prompt", required=True)
    submit.set_defaults(handler=_submit_audit)

    audit = subparsers.add_parser("audit", help="record strict VPS Codex audit JSON")
    audit.add_argument("task_id")
    audit.add_argument("--result-json")
    audit.add_argument("--result-file")
    audit.set_defaults(handler=_audit)

    complete = subparsers.add_parser("complete", help="mark an approved task as deployed")
    complete.add_argument("task_id")
    complete.set_defaults(handler=_complete)

    confirm = subparsers.add_parser("confirm", help="record explicit user approval for a sensitive task")
    confirm.add_argument("task_id")
    confirm.set_defaults(handler=_confirm)

    worker = subparsers.add_parser("worker", help="run a local Codex worker HTTP service")
    worker.add_argument("--worker-id", default="codex-worker")
    worker.add_argument("--role", type=WorkerRole, choices=list(WorkerRole), default=WorkerRole.IMPLEMENTER)
    worker.add_argument("--host", default=os.environ.get("CODEX_WORKER_HOST", "127.0.0.1"))
    worker.add_argument("--port", type=int, default=int(os.environ.get("CODEX_WORKER_PORT", "8765")))
    worker.add_argument("--token", default=os.environ.get("CODEX_WORKER_TOKEN", ""))
    worker.add_argument("--repo", default=os.environ.get("CODEX_REPO_PATH"))
    worker.add_argument("--command", default=os.environ.get("CODEX_COMMAND", "codex"))
    worker.add_argument("--sandbox", default=os.environ.get("CODEX_SANDBOX", "workspace-write"))
    worker.set_defaults(handler=_worker)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    raise SystemExit(main())
