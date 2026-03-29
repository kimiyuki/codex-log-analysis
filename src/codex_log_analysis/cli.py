from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .analysis import (
    build_report_payload,
    default_target_date,
    detect_sqlite_path,
    parse_date,
)
from .web import serve


def print_report(payload: dict[str, object]) -> int:
    target_date = payload["target_date"]
    stats = payload["stats"]
    sessions = payload["sessions"]
    print(f"# Codex session report ({target_date})")
    print(f"sessions: {stats['sessions']}")
    if not sessions:
        return 0

    print(f"user_prompts: {stats['user_prompts']}")
    print(f"archived_sessions: {stats['archived_sessions']}")
    issue_labels = ", ".join(group["issue_ref"] for group in payload["issue_groups"])
    print(f"issue_refs: {issue_labels if issue_labels else '-'}")
    print()

    for item in sessions:
        archived_display = "yes" if item["archived"] else "no"
        issue_refs = ", ".join(item["issue_refs"]) if item["issue_refs"] else "-"
        print(f"- {item['title']}")
        print(f"  session_id: {item['session_id']}")
        print(f"  archived: {archived_display}")
        print(f"  branch: {item['branch']}")
        print(f"  cwd: {item['cwd']}")
        print(f"  user_prompts: {item['user_prompts']}")
        print(f"  issue_refs: {issue_refs}")
        print(f"  first_prompt: {item['first_prompt']}")
        print(f"  keywords: {item['keyword_preview']}")
        print(f"  file: {item['file']}")
        print(f"  skill_signal_count: {item['skill_signal_count']}")
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex-log-analysis",
        description="Analyze Codex session snapshot JSONL files.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("sessions_snapshot"),
        help="snapshot root directory (default: %(default)s)",
    )
    parser.add_argument(
        "--archived-root",
        type=Path,
        default=Path("archived_sessions_snapshot"),
        help="archived snapshot root directory (default: %(default)s)",
    )
    parser.add_argument(
        "--sqlite",
        type=Path,
        default=None,
        help="SQLite metadata file path (default: auto-detect state*.sqlite in repo root)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    report_parser = subparsers.add_parser(
        "report",
        help="print a session summary for one day or for all sessions",
    )
    report_parser.add_argument(
        "--date",
        type=parse_date,
        default=default_target_date(),
        help="target date in YYYY-MM-DD (default: yesterday)",
    )
    report_parser.add_argument(
        "--all",
        action="store_true",
        help="analyze all available snapshot files",
    )
    report_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="max sessions to print (default: %(default)s)",
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="start a local web server with tabbed report views",
    )
    serve_parser.add_argument(
        "--date",
        type=parse_date,
        default=default_target_date(),
        help="initial target date in YYYY-MM-DD (default: yesterday)",
    )
    serve_parser.add_argument(
        "--all",
        action="store_true",
        help="start the UI in all-sessions mode",
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="bind host (default: %(default)s)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="bind port (default: %(default)s)",
    )
    serve_parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="max sessions returned by API per request (default: %(default)s)",
    )
    return parser


def resolve_sqlite_path(candidate: Path | None) -> Path | None:
    if candidate is not None:
        return candidate
    return detect_sqlite_path(Path.cwd())


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root: Path = args.root

    if not root.exists():
        parser.error(f"snapshot root does not exist: {root}")

    sqlite_path = resolve_sqlite_path(args.sqlite)

    if args.command == "report":
        target_date: date | None = None if args.all else args.date
        payload = build_report_payload(
            root=root,
            archived_root=args.archived_root,
            sqlite_path=sqlite_path,
            target_date=target_date,
            limit=args.limit,
        )
        return print_report(payload)

    if args.command == "serve":
        target_date = None if args.all else args.date
        serve(
            root=root,
            archived_root=args.archived_root,
            sqlite_path=sqlite_path,
            host=args.host,
            port=args.port,
            initial_date=target_date,
            limit=args.limit,
        )
        return 0

    parser.error(f"unsupported command: {args.command}")
    return 2
