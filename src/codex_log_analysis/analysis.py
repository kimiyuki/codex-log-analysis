from __future__ import annotations

import json
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

ISSUE_PATTERN = re.compile(r"(?:#|GH-?|issue\s+)(\d+)", re.IGNORECASE)
META_PROMPT_PREFIXES = ("<user_instructions>", "<environment_context>")
META_PROMPT_LINE_PREFIXES = ("# AGENTS.md instructions for ",)
SKILL_PATTERN = re.compile(r"\bskill\b|skill化|スキル化", re.IGNORECASE)
WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{3,}")
STOPWORDS = {
    "this",
    "that",
    "with",
    "from",
    "have",
    "will",
    "what",
    "when",
    "where",
    "which",
    "using",
    "would",
    "could",
    "should",
    "about",
    "there",
    "their",
    "github",
    "issue",
    "issues",
    "skill",
    "skills",
    "codex",
    "session",
    "sessions",
    "snapshot",
    "jsonl",
    "user",
    "assistant",
    "response",
}


@dataclass
class SessionSummary:
    session_id: str
    path: Path
    timestamp: str | None = None
    cwd: str | None = None
    title: str | None = None
    git_branch: str | None = None
    created_at: int | None = None
    first_user_message: str | None = None
    archived: bool = False
    archived_at: int | None = None
    first_prompt: str | None = None
    prompt_count: int = 0
    issue_refs: set[str] = field(default_factory=set)
    skill_mentions: int = 0
    keyword_counts: Counter[str] = field(default_factory=Counter)
    subagent_parent_session_id: str | None = None
    subagent_depth: int | None = None
    subagent_nickname: str | None = None
    subagent_role: str | None = None

    @property
    def prompt_preview(self) -> str:
        if not self.first_prompt:
            return "(実ユーザープロンプトなし)"
        text = normalize_whitespace(self.first_prompt)
        return truncate(text, 120)

    @property
    def title_preview(self) -> str:
        if not self.title:
            return self.prompt_preview
        return truncate(normalize_whitespace(self.title), 120)

    @property
    def keyword_preview(self) -> str:
        words = [word for word, _ in self.keyword_counts.most_common(5)]
        return ", ".join(words) if words else "-"

    @property
    def is_subagent_session(self) -> bool:
        return self.subagent_parent_session_id is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "title": self.title_preview,
            "full_title": self.title,
            "archived": self.archived,
            "branch": self.git_branch or "-",
            "cwd": self.cwd or "-",
            "user_prompts": self.prompt_count,
            "issue_refs": [f"#{ref}" for ref in sorted(self.issue_refs, key=int)],
            "first_prompt": self.prompt_preview,
            "keywords": [word for word, _ in self.keyword_counts.most_common(5)],
            "keyword_preview": self.keyword_preview,
            "file": str(self.path),
            "skill_signal_count": self.skill_mentions,
            "created_at": self.created_at,
            "timestamp": self.timestamp,
            "is_subagent_session": self.is_subagent_session,
            "subagent_parent_session_id": self.subagent_parent_session_id,
            "subagent_depth": self.subagent_depth,
            "subagent_nickname": self.subagent_nickname,
            "subagent_role": self.subagent_role,
        }


@dataclass
class IssueGroup:
    issue_ref: str
    session_ids: set[str] = field(default_factory=set)
    titles: list[str] = field(default_factory=list)
    archived_count: int = 0
    active_count: int = 0
    total_prompts: int = 0
    latest_created_at: int = 0

    @property
    def issue_label(self) -> str:
        return f"#{self.issue_ref}"

    def to_dict(self) -> dict[str, object]:
        unique_titles: list[str] = []
        for title in self.titles:
            if title not in unique_titles:
                unique_titles.append(title)
        return {
            "issue_ref": self.issue_label,
            "sessions_count": len(self.session_ids),
            "active_count": self.active_count,
            "archived_count": self.archived_count,
            "total_prompts": self.total_prompts,
            "titles": unique_titles[:5],
            "latest_created_at": self.latest_created_at,
        }


@dataclass
class ConversationMessage:
    index: int
    role: str
    text: str
    timestamp: str | None = None
    display_role: str | None = None
    is_subagent_context: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "role": self.role,
            "text": self.text,
            "timestamp": self.timestamp,
            "display_role": self.display_role or self.role,
            "is_subagent_context": self.is_subagent_context,
        }


def normalize_whitespace(text: str) -> str:
    return " ".join(text.split())


def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def default_target_date() -> date:
    return date.today() - timedelta(days=1)


def extract_content_text(content: object) -> Iterable[str]:
    if not isinstance(content, list):
        return []
    texts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str) and text.strip():
                texts.append(text)
    return texts


def join_content_text(content: object) -> str | None:
    texts = [text.strip() for text in extract_content_text(content) if text.strip()]
    if not texts:
        return None
    return "\n\n".join(texts)


def extract_words(text: str) -> Iterable[str]:
    for raw in WORD_PATTERN.findall(text):
        word = raw.lower()
        if word in STOPWORDS:
            continue
        yield word


def is_meta_prompt(text: str) -> bool:
    stripped = text.lstrip()
    if stripped.startswith(META_PROMPT_PREFIXES):
        return True
    return stripped.startswith(META_PROMPT_LINE_PREFIXES)


def iter_session_files(
    root: Path,
    target_date: date | None,
    archived: bool = False,
) -> list[Path]:
    if not root.exists():
        return []

    if archived:
        candidates = sorted(root.rglob("*.jsonl"))
        if target_date is None:
            return candidates
        marker = f"rollout-{target_date:%Y-%m-%d}T"
        return [path for path in candidates if marker in path.name]

    if target_date is None:
        return sorted(root.rglob("*.jsonl"))
    dated_root = root / f"{target_date:%Y}" / f"{target_date:%m}" / f"{target_date:%d}"
    if not dated_root.exists():
        return []
    return sorted(dated_root.rglob("*.jsonl"))


def summarize_file(path: Path) -> SessionSummary | None:
    summary: SessionSummary | None = None
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(
                        f"warn: {path}:{line_number}: invalid json: {exc}",
                        file=sys.stderr,
                    )
                    continue

                record_type = record.get("type")
                payload = record.get("payload")

                if record_type == "session_meta" and isinstance(payload, dict):
                    session_id = payload.get("id")
                    if not isinstance(session_id, str) or not session_id:
                        raise ValueError(f"{path}: session_meta.payload.id is missing")
                    summary = summary or SessionSummary(session_id=session_id, path=path)
                    summary.timestamp = payload.get("timestamp")
                    summary.cwd = payload.get("cwd")
                    source = payload.get("source")
                    if isinstance(source, dict):
                        subagent = source.get("subagent")
                        if isinstance(subagent, dict):
                            thread_spawn = subagent.get("thread_spawn")
                            if isinstance(thread_spawn, dict):
                                parent_thread_id = thread_spawn.get("parent_thread_id")
                                if isinstance(parent_thread_id, str) and parent_thread_id:
                                    summary.subagent_parent_session_id = parent_thread_id
                                depth = thread_spawn.get("depth")
                                if isinstance(depth, int):
                                    summary.subagent_depth = depth
                                agent_nickname = thread_spawn.get("agent_nickname")
                                if isinstance(agent_nickname, str) and agent_nickname:
                                    summary.subagent_nickname = agent_nickname
                                agent_role = thread_spawn.get("agent_role")
                                if isinstance(agent_role, str) and agent_role:
                                    summary.subagent_role = agent_role

                    if summary.subagent_nickname is None:
                        agent_nickname = payload.get("agent_nickname")
                        if isinstance(agent_nickname, str) and agent_nickname:
                            summary.subagent_nickname = agent_nickname
                    if summary.subagent_role is None:
                        agent_role = payload.get("agent_role")
                        if isinstance(agent_role, str) and agent_role:
                            summary.subagent_role = agent_role
                    continue

                if summary is None:
                    continue

                texts: list[str] = []
                if record_type == "response_item" and isinstance(payload, dict):
                    payload_type = payload.get("type")
                    role = payload.get("role")
                    if payload_type == "message" and role == "user":
                        texts = list(extract_content_text(payload.get("content")))
                        for text in texts:
                            if is_meta_prompt(text):
                                continue
                            summary.prompt_count += 1
                            if summary.first_prompt is None:
                                summary.first_prompt = text
                    elif payload_type == "message":
                        texts = list(extract_content_text(payload.get("content")))
                elif record_type == "event_msg" and isinstance(payload, dict):
                    message = payload.get("message")
                    if isinstance(message, str):
                        texts = [message]

                for text in texts:
                    summary.issue_refs.update(ISSUE_PATTERN.findall(text))
                    if SKILL_PATTERN.search(text):
                        summary.skill_mentions += 1
                    summary.keyword_counts.update(extract_words(text))

    except OSError as exc:
        print(f"warn: failed to read {path}: {exc}", file=sys.stderr)
        return None

    return summary


def detect_sqlite_path(root: Path) -> Path | None:
    candidates = sorted(root.glob("state*.sqlite"))
    if candidates:
        return candidates[-1]
    return None


def load_thread_metadata(sqlite_path: Path, session_ids: list[str]) -> dict[str, dict[str, object]]:
    if not session_ids:
        return {}

    placeholders = ", ".join("?" for _ in session_ids)
    query = (
        "SELECT id, title, git_branch, created_at, cwd, first_user_message, archived, archived_at "
        f"FROM threads WHERE id IN ({placeholders})"
    )

    metadata: dict[str, dict[str, object]] = {}
    try:
        connection = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise RuntimeError(f"failed to open sqlite metadata: {sqlite_path}: {exc}") from exc

    try:
        cursor = connection.execute(query, session_ids)
        for row in cursor:
            metadata[str(row[0])] = {
                "title": row[1],
                "git_branch": row[2],
                "created_at": row[3],
                "cwd": row[4],
                "first_user_message": row[5],
                "archived": row[6],
                "archived_at": row[7],
            }
    except sqlite3.DatabaseError as exc:
        raise RuntimeError(f"failed to read sqlite metadata: {sqlite_path}: {exc}") from exc
    finally:
        connection.close()

    return metadata


def apply_thread_metadata(
    summaries: list[SessionSummary],
    metadata: dict[str, dict[str, object]],
) -> None:
    for summary in summaries:
        row = metadata.get(summary.session_id)
        if row is None:
            continue
        title = row.get("title")
        if isinstance(title, str) and title.strip():
            summary.title = title
            summary.issue_refs.update(ISSUE_PATTERN.findall(title))
            summary.keyword_counts.update(extract_words(title))
        git_branch = row.get("git_branch")
        if isinstance(git_branch, str) and git_branch.strip():
            summary.git_branch = git_branch
        created_at = row.get("created_at")
        if isinstance(created_at, int):
            summary.created_at = created_at
        archived = row.get("archived")
        summary.archived = bool(archived)
        archived_at = row.get("archived_at")
        if isinstance(archived_at, int):
            summary.archived_at = archived_at
        cwd = row.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            summary.cwd = cwd
        first_user_message = row.get("first_user_message")
        if isinstance(first_user_message, str) and first_user_message.strip():
            summary.first_user_message = first_user_message


def collect_summaries(
    root: Path,
    archived_root: Path,
    sqlite_path: Path | None,
    target_date: date | None,
) -> list[SessionSummary]:
    files = iter_session_files(root, target_date)
    archived_files = iter_session_files(archived_root, target_date, archived=True)
    summary_by_id: dict[str, SessionSummary] = {}
    for path in [*files, *archived_files]:
        summary = summarize_file(path)
        if summary is None:
            continue
        summary_by_id[summary.session_id] = summary
    summaries = list(summary_by_id.values())
    if sqlite_path is not None and sqlite_path.exists():
        metadata = load_thread_metadata(sqlite_path, [item.session_id for item in summaries])
        apply_thread_metadata(summaries, metadata)
    summaries.sort(
        key=lambda item: (item.created_at if item.created_at is not None else 0, item.timestamp or ""),
        reverse=True,
    )
    return summaries


def resolve_session_path(
    root: Path,
    archived_root: Path,
    session_id: str,
    file_hint: str | None = None,
) -> Path:
    roots = [base.resolve() for base in (root, archived_root) if base.exists()]

    if file_hint:
        candidate = Path(file_hint)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        candidate = candidate.resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"session file does not exist: {file_hint}")
        if session_id not in candidate.name:
            raise ValueError(f"session file does not match session id: {file_hint}")
        if not any(candidate.is_relative_to(base) for base in roots):
            raise ValueError(f"session file is outside snapshot roots: {file_hint}")
        return candidate

    matches: list[Path] = []
    for base in (root, archived_root):
        if not base.exists():
            continue
        matches.extend(sorted(base.rglob(f"*{session_id}.jsonl")))

    unique_matches: list[Path] = []
    seen: set[Path] = set()
    for match in matches:
        resolved = match.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_matches.append(resolved)

    if not unique_matches:
        raise FileNotFoundError(f"session file not found for id: {session_id}")
    if len(unique_matches) > 1:
        joined = ", ".join(str(path) for path in unique_matches)
        raise RuntimeError(f"multiple session files found for {session_id}: {joined}")
    return unique_matches[0]


def load_conversation_messages(path: Path, summary: SessionSummary | None = None) -> list[ConversationMessage]:
    messages: list[ConversationMessage] = []
    is_subagent_session = bool(summary and summary.is_subagent_session)
    subagent_nickname = summary.subagent_nickname if summary is not None else None
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line_number, line in enumerate(fh, start=1):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(
                        f"warn: {path}:{line_number}: invalid json: {exc}",
                        file=sys.stderr,
                    )
                    continue

                if record.get("type") != "response_item":
                    continue
                payload = record.get("payload")
                if not isinstance(payload, dict):
                    continue
                if payload.get("type") != "message":
                    continue

                role = payload.get("role")
                if role not in {"user", "assistant"}:
                    continue

                text = join_content_text(payload.get("content"))
                if text is None:
                    continue
                if role == "user" and is_meta_prompt(text):
                    continue

                timestamp = record.get("timestamp")
                display_role = role
                if is_subagent_session:
                    if role == "user":
                        display_role = "parent agent"
                    else:
                        display_role = f"sub agent: {subagent_nickname}" if subagent_nickname else "sub agent"
                messages.append(
                    ConversationMessage(
                        index=len(messages) + 1,
                        role=role,
                        text=text,
                        timestamp=timestamp if isinstance(timestamp, str) else None,
                        display_role=display_role,
                        is_subagent_context=is_subagent_session,
                    )
                )
    except OSError as exc:
        raise RuntimeError(f"failed to read session detail: {path}: {exc}") from exc

    return messages


def group_by_issue(summaries: list[SessionSummary]) -> list[IssueGroup]:
    groups: dict[str, IssueGroup] = {}
    for summary in summaries:
        for issue_ref in summary.issue_refs:
            group = groups.setdefault(issue_ref, IssueGroup(issue_ref=issue_ref))
            group.session_ids.add(summary.session_id)
            group.titles.append(summary.title_preview)
            group.total_prompts += summary.prompt_count
            if summary.archived:
                group.archived_count += 1
            else:
                group.active_count += 1
            if summary.created_at is not None and summary.created_at > group.latest_created_at:
                group.latest_created_at = summary.created_at
    return sorted(
        groups.values(),
        key=lambda item: (item.latest_created_at, int(item.issue_ref)),
        reverse=True,
    )


def build_report_payload(
    root: Path,
    archived_root: Path,
    sqlite_path: Path | None,
    target_date: date | None,
    limit: int | None = None,
) -> dict[str, object]:
    summaries = collect_summaries(root, archived_root, sqlite_path, target_date)
    if limit is not None:
        summaries = summaries[:limit]
    active_sessions = [item for item in summaries if not item.archived]
    archived_sessions = [item for item in summaries if item.archived]
    issue_groups = group_by_issue(summaries)
    return {
        "target_date": target_date.isoformat() if target_date else "all",
        "stats": {
            "sessions": len(summaries),
            "active_sessions": len(active_sessions),
            "archived_sessions": len(archived_sessions),
            "user_prompts": sum(item.prompt_count for item in summaries),
            "issue_refs": len(issue_groups),
        },
        "sessions": [item.to_dict() for item in summaries],
        "active_sessions": [item.to_dict() for item in active_sessions],
        "archived_sessions": [item.to_dict() for item in archived_sessions],
        "issue_groups": [item.to_dict() for item in issue_groups],
    }


def build_session_detail_payload(
    root: Path,
    archived_root: Path,
    sqlite_path: Path | None,
    session_id: str,
    file_hint: str | None = None,
) -> dict[str, object]:
    path = resolve_session_path(
        root=root,
        archived_root=archived_root,
        session_id=session_id,
        file_hint=file_hint,
    )
    summary = summarize_file(path)
    if summary is None:
        raise RuntimeError(f"failed to summarize session file: {path}")

    if sqlite_path is not None and sqlite_path.exists():
        metadata = load_thread_metadata(sqlite_path, [summary.session_id])
        apply_thread_metadata([summary], metadata)

    conversation = load_conversation_messages(path, summary)
    return {
        "session": summary.to_dict(),
        "conversation": [item.to_dict() for item in conversation],
        "stats": {
            "messages": len(conversation),
            "user_messages": sum(1 for item in conversation if item.role == "user"),
            "assistant_messages": sum(1 for item in conversation if item.role == "assistant"),
        },
    }
