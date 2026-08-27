"""CLI for the standalone JUNMAI/Codex read-only chat worker."""

from __future__ import annotations

import argparse
import os
from typing import Sequence

from .codex_chat import ChatWorkerHTTPServer, worker_from_environment


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-chat")
    subparsers = parser.add_subparsers(dest="command", required=True)

    chat = subparsers.add_parser("chat", help="answer one prompt through read-only Codex")
    chat.add_argument("prompt", help="the only input accepted by the chat worker")
    chat.set_defaults(handler=_chat)

    serve = subparsers.add_parser("serve", help="serve the authenticated prompt-only HTTP API")
    serve.add_argument("--host", default=os.environ.get("CODEX_CHAT_HOST", "127.0.0.1"))
    serve.add_argument("--port", type=int, default=int(os.environ.get("CODEX_CHAT_PORT", "8777")))
    serve.set_defaults(handler=_serve)
    return parser


def _chat(args: argparse.Namespace) -> int:
    print(worker_from_environment().answer(args.prompt))
    return 0


def _serve(args: argparse.Namespace) -> int:
    server = ChatWorkerHTTPServer(
        worker_from_environment(), args.host, args.port, os.environ.get("CODEX_CHAT_WORKER_TOKEN", "")
    )
    print(f"codex-chat listening on {args.host}:{server.server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.shutdown()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
