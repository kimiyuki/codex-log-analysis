from __future__ import annotations

import argparse
from pathlib import Path

from .exporter import detect_sqlite_path, export_notes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codex_log_export",
        description="Export Codex session logs to Obsidian-friendly Markdown notes.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export_parser = subparsers.add_parser(
        "export",
        help="scan input logs and render Markdown notes",
    )
    export_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="input file or directory containing JSON / JSONL session logs",
    )
    export_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="directory where Markdown files will be written",
    )
    export_parser.add_argument(
        "--mode",
        choices=("note",),
        default="note",
        help="render mode (default: %(default)s)",
    )
    export_parser.add_argument(
        "--overwrite",
        action="store_true",
        help="overwrite existing Markdown files under output",
    )
    export_parser.add_argument(
        "--stdout",
        action="store_true",
        help="print a single rendered note to stdout instead of writing files",
    )
    export_parser.add_argument(
        "--sqlite",
        type=Path,
        default=None,
        help="SQLite metadata file path (default: auto-detect state*.sqlite in cwd)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "export":
        parser.error(f"unsupported command: {args.command}")

    input_path: Path = args.input
    output_path: Path = args.output

    if not input_path.exists():
        parser.error(f"input path does not exist: {input_path}")
    if output_path.exists() and not output_path.is_dir():
        parser.error(f"output path is not a directory: {output_path}")
    sqlite_path = args.sqlite if args.sqlite is not None else detect_sqlite_path(Path.cwd())
    if args.sqlite is not None and not sqlite_path.exists():
        parser.error(f"sqlite file does not exist: {sqlite_path}")

    written = export_notes(
        input_path=input_path,
        output_path=output_path,
        mode=args.mode,
        overwrite=args.overwrite,
        stdout=args.stdout,
        sqlite_path=sqlite_path,
    )
    return 0 if written >= 0 else 1
