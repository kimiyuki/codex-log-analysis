from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

TIMESTAMP_RE = re.compile(r"rollout-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})")
SESSION_ID_RE = re.compile(r"([0-9a-f]{8,}(?:-[0-9a-f]{4,}){0,})$", re.IGNORECASE)

USER_PROMPTS = [
    "ダッシュボードの見出し文言を整えたいです。まず現状の構成を確認してください。",
    "一覧画面で重要な数値だけ先に見えるようにしたいです。最小差分で方針を考えてください。",
    "設定ページの説明が少し硬いので、社内向けに分かりやすく直したいです。",
    "デモ向けに導線を整理したいです。どこを先に触るべきか見てください。",
    "検索結果の表示が単調なので、情報の優先度が伝わる並びにしたいです。",
    "この画面は日次運用で使うので、迷わず操作できる流れに見直したいです。",
]

ASSISTANT_REPLIES = [
    "確認します。画面構成と主要な導線を整理してから、変更案を短くまとめます。",
    "把握しました。まずは現状を崩さずに改善できる箇所を洗い出します。",
    "見ていきます。デモで伝わりやすい順に、表示の意図を整理します。",
    "了解です。まずは利用者が最初に見る情報と次の操作を分けて考えます。",
]

FOLLOW_UPS = [
    "合わせて issue #{issue} の背景も踏まえて、見せ方を揃えたいです。",
    "必要なら skill化しやすい観点も軽く残してください。",
    "細かい実装よりも、まずは見た目の理解しやすさを優先したいです。",
    "一覧と詳細の関係が一目で分かるようにしておきたいです。",
]

ASSISTANT_FOLLOW_UPS = [
    "了解しました。影響範囲を広げずに、一覧と詳細のつながりが伝わる案に寄せます。",
    "承知しました。まずは情報の優先順位を整理して、必要なら後で issue に分けられる形にします。",
    "そうします。デモで迷いが出ないよう、視線の流れを意識してまとめます。",
]

CWDS = [
    "/Users/demo-user/projects/demo-suite/atlas-app",
    "/Users/demo-user/projects/demo-suite/harbor-console",
    "/Users/demo-user/projects/demo-suite/nova-dashboard",
    "/Users/demo-user/projects/demo-suite/linen-portal",
    "/Users/demo-user/projects/demo-suite/sprout-admin",
]


@dataclass(frozen=True)
class SessionSeed:
    path: Path
    index: int
    archived: bool

    @property
    def session_id(self) -> str:
        match = SESSION_ID_RE.search(self.path.stem)
        if match:
            return match.group(1)
        return f"demo-session-{self.index:06d}"

    @property
    def base_timestamp(self) -> datetime:
        match = TIMESTAMP_RE.search(self.path.name)
        if match:
            day, hh, mm, ss = match.groups()
            return datetime.strptime(f"{day}T{hh}:{mm}:{ss}", "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=UTC
            )
        return datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC) + timedelta(minutes=self.index)

    @property
    def cwd(self) -> str:
        return CWDS[self.index % len(CWDS)]


def isoformat_z(dt: datetime) -> str:
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_lines(seed: SessionSeed) -> list[str]:
    start = seed.base_timestamp
    issue_number = 100 + (seed.index % 24)
    first_prompt = USER_PROMPTS[seed.index % len(USER_PROMPTS)]
    first_reply = ASSISTANT_REPLIES[seed.index % len(ASSISTANT_REPLIES)]
    follow_up = FOLLOW_UPS[seed.index % len(FOLLOW_UPS)].format(issue=issue_number)
    follow_reply = ASSISTANT_FOLLOW_UPS[seed.index % len(ASSISTANT_FOLLOW_UPS)]

    records = [
        {
            "timestamp": isoformat_z(start),
            "type": "session_meta",
            "payload": {
                "id": seed.session_id,
                "timestamp": isoformat_z(start),
                "cwd": seed.cwd,
                "originator": "codex_demo_cli",
                "cli_version": "0.120.0-demo",
                "source": "cli",
                "model_provider": "openai",
            },
        },
        {
            "timestamp": isoformat_z(start + timedelta(seconds=2)),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": first_prompt}],
            },
        },
        {
            "timestamp": isoformat_z(start + timedelta(seconds=2)),
            "type": "event_msg",
            "payload": {"type": "user_message", "message": first_prompt, "images": []},
        },
        {
            "timestamp": isoformat_z(start + timedelta(seconds=7)),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": first_reply}],
            },
        },
        {
            "timestamp": isoformat_z(start + timedelta(seconds=11)),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": follow_up}],
            },
        },
        {
            "timestamp": isoformat_z(start + timedelta(seconds=17)),
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": follow_reply}],
            },
        },
    ]

    return [json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records]


def overwrite_root(root: Path) -> int:
    if not root.exists():
        return 0

    count = 0
    for index, path in enumerate(sorted(root.rglob("*.jsonl")), start=1):
        seed = SessionSeed(path=path, index=index, archived=root.name.startswith("archived"))
        path.write_text("".join(build_lines(seed)), encoding="utf-8")
        count += 1
    return count


def move_sqlite_out_of_the_way(sqlite_path: Path) -> Path | None:
    if not sqlite_path.exists():
        return None
    target = sqlite_path.with_name(sqlite_path.name + ".demo-disabled")
    counter = 1
    while target.exists():
        target = sqlite_path.with_name(sqlite_path.name + f".demo-disabled-{counter}")
        counter += 1
    sqlite_path.rename(target)
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Codex ログをデモ用の擬似 JSONL に置き換える")
    parser.add_argument(
        "--root",
        dest="roots",
        action="append",
        default=["sessions_snapshot", "archived_sessions_snapshot"],
        help="上書き対象の snapshot root。複数指定可。",
    )
    parser.add_argument(
        "--sqlite",
        default="state_5.sqlite",
        help="自動参照を避けるため退避する SQLite パス。",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    roots = [Path(value) for value in args.roots]
    sqlite_path = Path(args.sqlite)

    replaced_counts = {str(root): overwrite_root(root) for root in roots}
    moved_sqlite = move_sqlite_out_of_the_way(sqlite_path)

    print(
        json.dumps(
            {
                "replaced_counts": replaced_counts,
                "sqlite_moved_to": str(moved_sqlite) if moved_sqlite is not None else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
