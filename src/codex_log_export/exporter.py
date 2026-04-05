from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

META_PROMPT_PREFIXES = ("<user_instructions>", "<environment_context>")
META_PROMPT_LINE_PREFIXES = ("# AGENTS.md instructions for ",)
JSON_SEQUENCE_KEYS = ("messages", "records", "items", "events")
IMPORTANT_EVENT_TYPES = {
    "agent_message",
    "agent_reasoning",
    "task_started",
    "task_complete",
    "turn_aborted",
    "context_compacted",
}
TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}|[一-龥ぁ-んァ-ヶー]{2,}")
PHRASE_SPLIT_PATTERN = re.compile(r"[。\n]+")
STOPWORDS = {
    "assistant",
    "codex",
    "commentary",
    "command",
    "context",
    "cwd",
    "exec_command",
    "final",
    "jsonl",
    "markdown",
    "message",
    "messages",
    "note",
    "notes",
    "phase",
    "session",
    "summary",
    "tool",
    "tools",
    "user",
}


@dataclass
class MessageEntry:
    role: str
    text: str
    timestamp: str | None
    phase: str | None = None


@dataclass
class ToolEntry:
    name: str
    timestamp: str | None
    args: str | None = None
    output: str | None = None
    status: str | None = None


@dataclass
class TimelineEntry:
    timestamp: str | None
    label: str
    detail: str


@dataclass
class SessionNote:
    session_id: str
    source_file: Path
    created: str | None = None
    title: str | None = None
    cwd: str | None = None
    branch: str | None = None
    messages: list[MessageEntry] = field(default_factory=list)
    tools: list[ToolEntry] = field(default_factory=list)
    timeline: list[TimelineEntry] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def display_title(self) -> str:
        if self.title:
            return self.title
        return self.session_id


def export_notes(
    input_path: Path,
    output_path: Path,
    mode: str,
    overwrite: bool,
    stdout: bool,
    sqlite_path: Path | None,
) -> int:
    files = discover_log_files(input_path)
    if not files:
        raise RuntimeError(f"no JSON / JSONL files found under: {input_path}")

    notes: list[tuple[SessionNote, str]] = []
    for path in files:
        note = build_session_note(path, sqlite_path=sqlite_path)
        markdown = render_markdown(note, mode=mode)
        notes.append((note, markdown))

    if stdout:
        if len(notes) != 1:
            raise RuntimeError("--stdout requires exactly one input log file")
        print(notes[0][1], end="")
        return 1

    output_path.mkdir(parents=True, exist_ok=True)
    written = 0
    for note, markdown in notes:
        target = output_path / build_note_filename(note)
        if target.exists() and not overwrite:
            raise FileExistsError(f"output file already exists: {target}")
        target.write_text(markdown, encoding="utf-8")
        written += 1
    return written


def discover_log_files(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    return sorted(
        path
        for path in input_path.rglob("*")
        if path.is_file() and path.suffix.lower() in {".json", ".jsonl"}
    )


def detect_sqlite_path(root: Path) -> Path | None:
    candidates = sorted(root.glob("state*.sqlite"))
    if candidates:
        return candidates[-1]
    return None


def build_note_filename(note: SessionNote) -> str:
    return f"{note.session_id}.md"


def build_session_note(path: Path, sqlite_path: Path | None) -> SessionNote:
    records = load_records(path)
    session_id: str | None = None
    created: str | None = None
    title: str | None = None
    note = SessionNote(session_id="", source_file=path)
    pending_tools: dict[str, ToolEntry] = {}
    unsupported_items: list[str] = []

    for record in records:
        if not isinstance(record, dict):
            raise ValueError(f"{path}: record is not an object")

        record_type = record.get("type")
        timestamp = as_str(record.get("timestamp"))
        payload = record.get("payload")

        if record_type == "session_meta":
            if not isinstance(payload, dict):
                raise ValueError(f"{path}: session_meta payload is not an object")
            session_id = first_non_empty_str(payload.get("id"), session_id)
            created = first_non_empty_str(payload.get("timestamp"), created, timestamp)
            title = first_non_empty_str(
                payload.get("title"),
                title,
                extract_text_from_unknown(payload.get("title")),
            )
            continue

        if record_type == "response_item":
            if not isinstance(payload, dict):
                raise ValueError(f"{path}: response_item payload is not an object")
            payload_type = as_str(payload.get("type"))
            if payload_type == "message":
                role = as_str(payload.get("role"))
                if role is None:
                    raise ValueError(f"{path}: message payload.role is missing")
                text = join_content_text(payload.get("content"))
                if text is None:
                    unsupported_items.append("message-without-text")
                    continue
                note.messages.append(
                    MessageEntry(
                        role=role,
                        text=text,
                        timestamp=timestamp,
                        phase=as_str(payload.get("phase")),
                    )
                )
                note.timeline.append(
                    TimelineEntry(
                        timestamp=timestamp,
                        label=role.title(),
                        detail=preview(text),
                    )
                )
                if role == "user" and not is_meta_prompt(text) and title is None:
                    title = preview(text, 60)
                continue
            if payload_type in {"function_call", "custom_tool_call"}:
                name = as_str(payload.get("name"))
                if name is None:
                    raise ValueError(f"{path}: tool call name is missing")
                tool = ToolEntry(
                    name=name,
                    timestamp=timestamp,
                    args=extract_tool_args(payload),
                )
                call_id = as_str(payload.get("call_id"))
                if call_id:
                    pending_tools[call_id] = tool
                else:
                    note.tools.append(tool)
                note.timeline.append(
                    TimelineEntry(
                        timestamp=timestamp,
                        label="Tool",
                        detail=f"{name} called",
                    )
                )
                continue
            if payload_type in {"function_call_output", "custom_tool_call_output"}:
                call_id = as_str(payload.get("call_id"))
                if call_id and call_id in pending_tools:
                    tool = pending_tools.pop(call_id)
                    tool.output = extract_tool_output(payload)
                    tool.status = derive_tool_status(tool.output)
                    note.tools.append(tool)
                else:
                    note.tools.append(
                        ToolEntry(
                            name="unknown",
                            timestamp=timestamp,
                            output=extract_tool_output(payload),
                            status="unmatched_output",
                        )
                    )
                continue
            unsupported_items.append(f"response_item:{payload_type or 'unknown'}")
            continue

        if record_type == "event_msg":
            if not isinstance(payload, dict):
                raise ValueError(f"{path}: event_msg payload is not an object")
            event_type = as_str(payload.get("type"))
            detail = extract_event_detail(payload)
            if event_type in IMPORTANT_EVENT_TYPES and detail:
                note.timeline.append(
                    TimelineEntry(
                        timestamp=timestamp,
                        label=f"Event:{event_type}",
                        detail=preview(detail),
                    )
                )
            continue

        if record_type == "compacted":
            replacement_history = payload.get("replacement_history") if isinstance(payload, dict) else None
            history_count = len(replacement_history) if isinstance(replacement_history, list) else 0
            note.notes.append(f"context compacted in source log ({history_count} replacement entries)")
            note.timeline.append(
                TimelineEntry(
                    timestamp=timestamp,
                    label="Compacted",
                    detail=f"replacement_history={history_count}",
                )
            )
            continue

        unsupported_items.append(record_type or "unknown-record")

    for tool in pending_tools.values():
        tool.status = tool.status or "missing_output"
        note.tools.append(tool)

    if session_id is None:
        session_id = path.stem
        note.notes.append("session_id was not present in log; used source filename stem")
    note.session_id = session_id
    note.created = created
    note.title = title
    apply_sqlite_metadata(note, sqlite_path)

    if not note.messages:
        raise ValueError(f"{path}: no message records found")
    if unsupported_items:
        unique_items = ", ".join(sorted(set(unsupported_items)))
        note.notes.append(f"unsupported or skipped items: {unique_items}")
    if title is None:
        note.notes.append("title was not present in source log")
    return note


def load_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        return load_jsonl_records(path)
    if suffix == ".json":
        return load_json_records(path)
    raise ValueError(f"unsupported file extension: {path}")


def load_jsonl_records(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL record: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: record must be an object")
            records.append(value)
    return records


def load_json_records(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        try:
            data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid JSON: {exc}") from exc

    if isinstance(data, list):
        if not all(isinstance(item, dict) for item in data):
            raise ValueError(f"{path}: JSON array must contain objects only")
        return list(data)

    if isinstance(data, dict):
        if "type" in data and isinstance(data.get("payload"), dict):
            return [data]

        matches = [
            key
            for key in JSON_SEQUENCE_KEYS
            if isinstance(data.get(key), list)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"{path}: JSON object must contain exactly one supported record list key: {', '.join(JSON_SEQUENCE_KEYS)}"
            )
        sequence = data[matches[0]]
        if not all(isinstance(item, dict) for item in sequence):
            raise ValueError(f"{path}: {matches[0]} must contain objects only")
        return list(sequence)

    raise ValueError(f"{path}: unsupported JSON root type: {type(data).__name__}")


def apply_sqlite_metadata(note: SessionNote, sqlite_path: Path | None) -> None:
    if sqlite_path is None or not sqlite_path.exists():
        return

    row = load_thread_metadata(sqlite_path, note.session_id)
    if row is None:
        note.notes.append(f"sqlite metadata not found for session_id: {note.session_id}")
        return

    title = as_str(row.get("title"))
    if title is not None:
        note.title = title

    cwd = as_str(row.get("cwd"))
    if cwd is not None:
        note.cwd = cwd

    branch = as_str(row.get("git_branch"))
    if branch is not None:
        note.branch = branch

    if note.created is None:
        created_at = row.get("created_at")
        if isinstance(created_at, int):
            note.created = datetime.fromtimestamp(created_at, UTC).isoformat()


def load_thread_metadata(sqlite_path: Path, session_id: str) -> dict[str, Any] | None:
    query = (
        "SELECT id, title, git_branch, created_at, cwd "
        "FROM threads WHERE id = ?"
    )
    try:
        connection = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise RuntimeError(f"failed to open sqlite metadata: {sqlite_path}: {exc}") from exc

    try:
        row = connection.execute(query, (session_id,)).fetchone()
    except sqlite3.DatabaseError as exc:
        raise RuntimeError(f"failed to read sqlite metadata: {sqlite_path}: {exc}") from exc
    finally:
        connection.close()

    if row is None:
        return None

    return {
        "id": row[0],
        "title": row[1],
        "git_branch": row[2],
        "created_at": row[3],
        "cwd": row[4],
    }


def join_content_text(content: object) -> str | None:
    if not isinstance(content, list):
        return None
    texts = [extract_text_from_unknown(item) for item in content]
    normalized = [text.strip() for text in texts if text and text.strip()]
    if not normalized:
        return None
    return "\n\n".join(normalized)


def extract_text_from_unknown(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return None
    for key in ("text", "message"):
        text = value.get(key)
        if isinstance(text, str) and text.strip():
            return text
    return None


def extract_tool_args(payload: dict[str, Any]) -> str | None:
    for key in ("arguments", "input"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def extract_tool_output(payload: dict[str, Any]) -> str | None:
    output = payload.get("output")
    if isinstance(output, str) and output.strip():
        return output
    if output is None:
        return None
    return json.dumps(output, ensure_ascii=False, indent=2)


def derive_tool_status(output: str | None) -> str | None:
    if output is None:
        return None
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    metadata = parsed.get("metadata")
    if isinstance(metadata, dict):
        exit_code = metadata.get("exit_code")
        if isinstance(exit_code, int):
            return "error" if exit_code != 0 else "ok"
    return None


def extract_event_detail(payload: dict[str, Any]) -> str | None:
    for key in ("message", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def render_markdown(note: SessionNote, mode: str) -> str:
    messages = filter_messages(note.messages, mode=mode)
    summary_lines = build_summary_lines(note, messages, note.tools)
    keywords = extract_keywords(messages)
    key_phrases = extract_key_phrases(messages)
    selected_messages = select_messages(messages)
    tool_stats = summarize_tools(note.tools)
    created = note.created or "unknown"
    lines = [
        "---",
        "type: codex-log",
        f"session_id: {note.session_id}",
        f"created: {created}",
        f"source_file: {note.source_file}",
    ]
    if note.cwd:
        lines.append(f"cwd: {yaml_scalar(note.cwd)}")
    if note.branch:
        lines.append(f"branch: {yaml_scalar(note.branch)}")
    lines.extend([
        "tags:",
        "  - codex",
        "  - log",
        "---",
        "",
        f"# {note.display_title}",
        "",
        "## Summary",
    ])
    if summary_lines:
        for item in summary_lines:
            lines.append(f"- {item}")
    else:
        lines.append("- summary unavailable")

    lines.extend(["", "## Keywords"])
    if keywords:
        for item in keywords:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    lines.extend(["", "## Key Phrases"])
    if key_phrases:
        for item in key_phrases:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    lines.extend(["", "## Selected Messages"])
    if selected_messages:
        for item in selected_messages:
            lines.append(f"### {item.role.title()}")
            if item.timestamp:
                lines.append(f"_timestamp: {item.timestamp}_")
            if item.phase:
                lines.append(f"_phase: {item.phase}_")
            lines.append("")
            lines.append(item.text.rstrip())
            lines.append("")
    else:
        lines.append("- no selected messages")

    lines.extend(["## Tool Stats"])
    if tool_stats:
        for item in tool_stats:
            lines.append(f"- {item}")
    else:
        lines.append("- none")

    lines.append("## Notes")
    if note.notes:
        for item in note.notes:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def filter_messages(messages: list[MessageEntry], mode: str) -> list[MessageEntry]:
    filtered: list[MessageEntry] = []
    for item in messages:
        if item.role not in {"user", "assistant"}:
            continue
        if item.role == "user" and is_meta_prompt(item.text):
            continue
        if item.role == "assistant" and item.phase == "commentary":
            continue
        filtered.append(item)
    return filtered


def build_summary_lines(
    note: SessionNote,
    messages: list[MessageEntry],
    tools: list[ToolEntry],
) -> list[str]:
    first_user = next((item for item in messages if item.role == "user"), None)
    user_count = sum(1 for item in messages if item.role == "user")
    assistant_count = sum(1 for item in messages if item.role == "assistant")
    first_assistant = next((item for item in messages if item.role == "assistant"), None)
    last_assistant = next((item for item in reversed(messages) if item.role == "assistant"), None)
    parts: list[str] = []
    if first_user is not None:
        parts.append(f"依頼の起点: {preview(first_user.text, 100)}")
    if first_assistant is not None:
        parts.append(f"最初の応答: {preview(first_assistant.text, 100)}")
    if last_assistant is not None:
        parts.append(f"着地点: {preview(last_assistant.text, 100)}")
    parts.append(f"会話量: user {user_count}件 / assistant {assistant_count}件")
    if tools:
        parts.append(f"tool 利用: {format_tool_summary(tools)}")
    if note.cwd is not None:
        parts.append(f"作業場所: {note.cwd}")
    if note.branch is not None:
        parts.append(f"branch: {note.branch}")
    return parts


def format_tool_summary(tools: list[ToolEntry]) -> str:
    counter = Counter(tool.name for tool in tools)
    parts = [f"{name}={count}" for name, count in counter.most_common(4)]
    error_count = sum(1 for tool in tools if tool.status in {"error", "missing_output", "unmatched_output"})
    if error_count:
        parts.append(f"errors={error_count}")
    return ", ".join(parts)


def extract_keywords(messages: list[MessageEntry], limit: int = 8) -> list[str]:
    counter: Counter[str] = Counter()
    for item in messages:
        for token in TOKEN_PATTERN.findall(item.text):
            normalized = token.lower()
            if normalized in STOPWORDS:
                continue
            counter[token] += 1
    return [word for word, _ in counter.most_common(limit)]


def extract_key_phrases(messages: list[MessageEntry], limit: int = 6) -> list[str]:
    seen: set[str] = set()
    scored: list[tuple[int, str]] = []
    for item in messages:
        for raw_phrase in PHRASE_SPLIT_PATTERN.split(item.text):
            phrase = " ".join(raw_phrase.split())
            if len(phrase) < 12 or len(phrase) > 90:
                continue
            if is_meta_prompt(phrase):
                continue
            if phrase.startswith("- `") or "`" in phrase or "--" in phrase or "::" in phrase:
                continue
            if phrase in seen:
                continue
            seen.add(phrase)
            score = 0
            if item.role == "user":
                score += 3
            if item.role == "assistant" and item.phase == "final_answer":
                score += 4
            if phrase.startswith("- "):
                score += 1
            score += min(len(phrase) // 20, 3)
            scored.append((score, phrase))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [phrase for _, phrase in scored[:limit]]


def select_messages(messages: list[MessageEntry], limit: int = 4) -> list[MessageEntry]:
    if not messages:
        return []
    selected: list[MessageEntry] = []
    first_user = next((item for item in messages if item.role == "user"), None)
    final_assistant = next(
        (
            item
            for item in reversed(messages)
            if item.role == "assistant" and item.phase == "final_answer"
        ),
        None,
    )
    if first_user is not None:
        selected.append(first_user)
    first_assistant = next((item for item in messages if item.role == "assistant"), None)
    if first_assistant is not None and first_assistant not in selected:
        selected.append(first_assistant)
    if final_assistant is not None and final_assistant not in selected:
        selected.append(final_assistant)
    last_user = next((item for item in reversed(messages) if item.role == "user"), None)
    if last_user is not None and last_user not in selected:
        selected.append(last_user)
    return selected[:limit]


def summarize_tools(tools: list[ToolEntry]) -> list[str]:
    if not tools:
        return []
    counter = Counter(tool.name for tool in tools)
    lines = [f"{name}: {count}" for name, count in counter.most_common(8)]
    error_count = sum(1 for tool in tools if tool.status in {"error", "missing_output", "unmatched_output"})
    if error_count:
        lines.append(f"errors: {error_count}")
    return lines


def is_meta_prompt(text: str) -> bool:
    stripped = text.lstrip()
    if stripped.startswith(META_PROMPT_PREFIXES):
        return True
    return stripped.startswith(META_PROMPT_LINE_PREFIXES)


def preview(text: str, max_len: int = 120) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 3] + "..."


def as_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def first_non_empty_str(*values: object) -> str | None:
    for value in values:
        text = as_str(value)
        if text is not None:
            return text
    return None


def yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)
