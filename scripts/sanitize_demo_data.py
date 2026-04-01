from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

PATH_RE = re.compile(r'/(?:Users|home)/[^\s"\'<>`]+')
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SSH_URL_RE = re.compile(r"git@github\.com:([^/\s]+)/([^\s]+?)(?:\.git)?\b")
HTTPS_URL_RE = re.compile(r"https://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?\b")
WORDISH_RE = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{2,}")
WORKTREE_ID_RE = re.compile(r"^[0-9a-f]{4,}$", re.IGNORECASE)
UUIDISH_RE = re.compile(r"^[0-9a-f]{8,}$", re.IGNORECASE)
DATEISH_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")

GENERIC_SEGMENTS = {
    "",
    ".",
    "..",
    "Users",
    "home",
    "dev",
    "github",
    ".codex",
    "worktrees",
    "sessions_snapshot",
    "archived_sessions_snapshot",
    "src",
    "docs",
    "scripts",
    "script",
    "data",
    "tests",
    "test",
    "tmp",
    "dist",
    "build",
    "out",
    "app",
    "apps",
    "web",
    "lib",
    "bin",
    "cmd",
    "pkg",
    "internal",
    "node_modules",
    "main",
    "master",
    "feature",
    "features",
    "fix",
    "bugfix",
    "hotfix",
    "release",
    "staging",
    "production",
    "prod",
}

GENERIC_WORDS = {
    "agents",
    "api",
    "app",
    "apps",
    "assistant",
    "automation",
    "branch",
    "branches",
    "bug",
    "client",
    "cloudflare",
    "codex",
    "data",
    "daily",
    "demo",
    "develop",
    "development",
    "docker",
    "docs",
    "email",
    "feature",
    "github",
    "git",
    "issue",
    "issues",
    "jsonl",
    "line",
    "lines",
    "local",
    "main",
    "master",
    "memory",
    "message",
    "messages",
    "path",
    "paths",
    "prod",
    "production",
    "prompt",
    "prompts",
    "python",
    "readme",
    "repo",
    "repos",
    "report",
    "review",
    "run",
    "runs",
    "script",
    "scripts",
    "server",
    "session",
    "sessions",
    "skill",
    "skills",
    "snapshot",
    "sqlite",
    "sqlite3",
    "staging",
    "test",
    "tests",
    "title",
    "titles",
    "tool",
    "tools",
    "user",
    "users",
    "web",
}


class DemoSanitizer:
    def __init__(self) -> None:
        self.user_map: dict[str, str] = {}
        self.org_map: dict[str, str] = {}
        self.repo_map: dict[str, str] = {}
        self.worktree_map: dict[str, str] = {}
        self.branch_map: dict[str, str] = {}
        self.email_map: dict[str, str] = {}
        self.term_map: dict[str, str] = {}
        self.found_terms: set[str] = set()
        self.found_branches: set[str] = set()

    def user_alias(self, name: str) -> str:
        return self.user_map.setdefault(name, f"user-{len(self.user_map) + 1:02d}")

    def org_alias(self, name: str) -> str:
        return self.org_map.setdefault(name, f"org-{len(self.org_map) + 1:02d}")

    def repo_alias(self, name: str) -> str:
        return self.repo_map.setdefault(name, f"app-{len(self.repo_map) + 1:03d}")

    def worktree_alias(self, name: str) -> str:
        return self.worktree_map.setdefault(name, f"wt-{len(self.worktree_map) + 1:03d}")

    def branch_alias(self, name: str) -> str:
        return self.branch_map.setdefault(name, f"demo-branch-{len(self.branch_map) + 1:03d}")

    def email_alias(self, address: str) -> str:
        return self.email_map.setdefault(address, f"user{len(self.email_map) + 1:03d}@example.test")

    def should_collect_term(self, token: str) -> bool:
        lowered = token.lower()
        if lowered in GENERIC_WORDS:
            return False
        if DATEISH_RE.match(token):
            return False
        if UUIDISH_RE.match(token):
            return False
        if token.isdigit():
            return False
        if token.startswith(("app-", "org-", "user-", "wt-")):
            return False
        return len(token) > 3

    def collect_terms_from_segment(self, segment: str) -> None:
        raw = segment.strip()
        if not raw or raw in GENERIC_SEGMENTS or WORKTREE_ID_RE.match(raw):
            return

        stem = raw
        if "." in stem and not stem.startswith("."):
            stem = stem.rsplit(".", 1)[0]

        candidates = {raw, stem}
        candidates.update(
            part for part in re.split(r"[-_.]+", stem) if self.should_collect_term(part)
        )

        for candidate in candidates:
            if self.should_collect_term(candidate):
                self.found_terms.add(candidate)

    def collect_from_path(self, path_text: str) -> None:
        parts = [part for part in path_text.split("/") if part]
        if not parts:
            return

        if parts[0] in {"Users", "home"} and len(parts) >= 2:
            self.user_alias(parts[1])

        for index, part in enumerate(parts):
            if part in {"Users", "home"}:
                continue
            if index >= 2 and parts[index - 1] == "github":
                self.org_alias(part)
                continue
            if index >= 3 and parts[index - 2] == "github":
                self.repo_alias(part)
                self.collect_terms_from_segment(part)
                continue
            if index >= 2 and parts[index - 1] == "worktrees":
                self.worktree_alias(part)
                continue
            if index >= 3 and parts[index - 2] == "worktrees":
                self.repo_alias(part)
                self.collect_terms_from_segment(part)
                continue
            self.collect_terms_from_segment(part)

    def collect_from_string(self, text: str) -> None:
        for match in PATH_RE.finditer(text):
            self.collect_from_path(match.group(0))

        for match in SSH_URL_RE.finditer(text):
            owner, repo = match.groups()
            self.org_alias(owner)
            self.repo_alias(repo.removesuffix(".git"))
            self.collect_terms_from_segment(owner)
            self.collect_terms_from_segment(repo)

        for match in HTTPS_URL_RE.finditer(text):
            owner, repo = match.groups()
            self.org_alias(owner)
            self.repo_alias(repo.removesuffix(".git"))
            self.collect_terms_from_segment(owner)
            self.collect_terms_from_segment(repo)

        for match in EMAIL_RE.finditer(text):
            self.email_alias(match.group(0))

    def scan_jsonl_roots(self, roots: list[Path]) -> None:
        for root in roots:
            if not root.exists():
                continue
            for path in root.rglob("*.jsonl"):
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        self.collect_from_string(line)

    def scan_sqlite(self, sqlite_path: Path) -> None:
        connection = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
        try:
            tables = [
                row[0]
                for row in connection.execute(
                    "select name from sqlite_master where type='table' order by name"
                )
            ]
            for table in tables:
                text_columns = [
                    row[1]
                    for row in connection.execute(f"pragma table_info({table})")
                    if row[2].upper() == "TEXT"
                ]
                if not text_columns:
                    continue
                query = "select " + ", ".join(text_columns) + f" from {table}"
                for row in connection.execute(query):
                    for value in row:
                        if isinstance(value, str):
                            self.collect_from_string(value)

            for branch, in connection.execute(
                "select distinct git_branch from threads where git_branch is not null and git_branch <> ''"
            ):
                if branch not in {"main", "master", "develop", "dev", "trunk"}:
                    self.found_branches.add(branch)
        finally:
            connection.close()

    def finalize_term_map(self) -> None:
        for token in sorted(self.found_terms, key=lambda value: (value.lower(), len(value))):
            if token in self.repo_map or token in self.org_map or token in self.user_map:
                continue
            self.term_map.setdefault(token, f"term-{len(self.term_map) + 1:03d}")

    def sanitize_path(self, path_text: str) -> str:
        parts = [part for part in path_text.split("/") if part]
        if not parts:
            return path_text

        new_parts: list[str] = []
        index = 0
        if parts[0] in {"Users", "home"} and len(parts) >= 2:
            new_parts.extend([parts[0], self.user_alias(parts[1])])
            index = 2

        while index < len(parts):
            part = parts[index]
            if part == "github" and index + 2 < len(parts):
                new_parts.append(part)
                new_parts.append(self.org_alias(parts[index + 1]))
                new_parts.append(self.repo_alias(parts[index + 2]))
                index += 3
                continue
            if part == "worktrees" and index + 2 < len(parts):
                new_parts.append(part)
                new_parts.append(self.worktree_alias(parts[index + 1]))
                new_parts.append(self.repo_alias(parts[index + 2]))
                index += 3
                continue

            if part in GENERIC_SEGMENTS or UUIDISH_RE.match(part) or DATEISH_RE.match(part):
                new_parts.append(part)
                index += 1
                continue

            stem, dot, suffix = part.partition(".") if "." in part and not part.startswith(".") else (
                part,
                "",
                "",
            )
            replacement = stem
            if stem in self.repo_map:
                replacement = self.repo_alias(stem)
            elif stem in self.org_map:
                replacement = self.org_alias(stem)
            elif stem in self.user_map:
                replacement = self.user_alias(stem)
            elif stem in self.worktree_map:
                replacement = self.worktree_alias(stem)
            elif stem in self.term_map:
                replacement = self.term_map[stem]

            new_parts.append(replacement + (dot + suffix if dot else ""))
            index += 1

        return "/" + "/".join(new_parts)

    def sanitize_text(self, text: str) -> str:
        if not text:
            return text

        sanitized = EMAIL_RE.sub(lambda match: self.email_alias(match.group(0)), text)

        def replace_ssh(match: re.Match[str]) -> str:
            owner, repo = match.groups()
            return (
                f"git@github.com:{self.org_alias(owner)}/{self.repo_alias(repo.removesuffix('.git'))}.git"
            )

        def replace_https(match: re.Match[str]) -> str:
            owner, repo = match.groups()
            return (
                f"https://github.com/{self.org_alias(owner)}/{self.repo_alias(repo.removesuffix('.git'))}.git"
            )

        sanitized = SSH_URL_RE.sub(replace_ssh, sanitized)
        sanitized = HTTPS_URL_RE.sub(replace_https, sanitized)
        sanitized = PATH_RE.sub(lambda match: self.sanitize_path(match.group(0)), sanitized)

        for branch in sorted(self.found_branches, key=len, reverse=True):
            sanitized = sanitized.replace(branch, self.branch_alias(branch))

        for token in sorted(self.term_map, key=len, reverse=True):
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])")
            sanitized = pattern.sub(self.term_map[token], sanitized)

        return sanitized

def rewrite_jsonl_files(roots: list[Path], sanitizer: DemoSanitizer, apply: bool) -> int:
    changed_files = 0
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.jsonl"):
            changed = False
            new_lines: list[str] = []
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    sanitized = sanitizer.sanitize_text(line.rstrip("\n"))
                    if sanitized != line.rstrip("\n"):
                        changed = True
                    new_lines.append(sanitized + "\n")

            if changed:
                changed_files += 1
                if apply:
                    path.write_text("".join(new_lines), encoding="utf-8")
    return changed_files


def rewrite_sqlite(sqlite_path: Path, sanitizer: DemoSanitizer, apply: bool) -> int:
    connection = sqlite3.connect(sqlite_path)
    try:
        connection.execute("pragma busy_timeout=5000")
        tables = [
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type='table' order by name"
            )
        ]
        changed_rows = 0
        for table in tables:
            info = list(connection.execute(f"pragma table_info({table})"))
            text_columns = [row[1] for row in info if row[2].upper() == "TEXT"]
            if not text_columns:
                continue

            query = "select rowid, " + ", ".join(text_columns) + f" from {table}"
            for row in connection.execute(query):
                rowid = row[0]
                updates: dict[str, str] = {}
                for column, value in zip(text_columns, row[1:]):
                    if isinstance(value, str):
                        sanitized = sanitizer.sanitize_text(value)
                        if sanitized != value:
                            updates[column] = sanitized
                if not updates:
                    continue

                changed_rows += 1
                if apply:
                    assignments = ", ".join(f"{column}=?" for column in updates)
                    connection.execute(
                        f"update {table} set {assignments} where rowid=?",
                        [*updates.values(), rowid],
                    )

        if apply:
            connection.commit()
        return changed_rows
    finally:
        connection.close()


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="sessions_snapshot と state_5.sqlite をデモ用の擬似名に匿名化する",
    )
    parser.add_argument(
        "--root",
        dest="roots",
        action="append",
        default=["sessions_snapshot", "archived_sessions_snapshot"],
        help="匿名化対象の JSONL ルート。複数回指定可。",
    )
    parser.add_argument(
        "--sqlite",
        default="state_5.sqlite",
        help="匿名化対象の SQLite ファイル。",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="実際に上書きする。未指定時は dry-run。",
    )
    return parser


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    roots = [Path(value) for value in args.roots]
    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        raise SystemExit(f"sqlite not found: {sqlite_path}")

    sanitizer = DemoSanitizer()
    sanitizer.scan_jsonl_roots(roots)
    sanitizer.scan_sqlite(sqlite_path)
    sanitizer.finalize_term_map()

    changed_jsonl_files = rewrite_jsonl_files(roots, sanitizer, apply=args.apply)
    changed_sqlite_rows = rewrite_sqlite(sqlite_path, sanitizer, apply=args.apply)

    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "changed_jsonl_files": changed_jsonl_files,
                "changed_sqlite_rows": changed_sqlite_rows,
                "user_aliases": sanitizer.user_map,
                "org_aliases": sanitizer.org_map,
                "repo_aliases": sanitizer.repo_map,
                "worktree_aliases": sanitizer.worktree_map,
                "branch_alias_count": len(sanitizer.branch_map),
                "email_alias_count": len(sanitizer.email_map),
                "term_alias_count": len(sanitizer.term_map),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
