# Codex session log から 振り返りをする

以下の command で `sessions_snapshot` の JSONL ファイルを持ってきて、分析をする。
`rsync -av --exclude '*.lock' ~/.codex/sessions/ ./sessions_snapshot/`
`rsync -av ~/.codex/state_5.sqlite ./`


## 例
- 昨日行ったセッションについて、title,branch,自分のprompt回数,github issueとの結び付き, その他有用なやり取りの紹介　などをterminalで確認
- やりとりの中でskill化余地の提言を行う

## 初期セットアップ

この repo は Python + `uv` 前提で、依存は標準ライブラリのみです。

`sessions_snapshot/` の JSONL に加えて、`archived_sessions_snapshot/` と Codex のメタデータを持つ `state_*.sqlite` を repo 直下へ rsync してある前提です。`report` はこの SQLite を自動検出して、タイトルや branch を補完し、通常セッションと archived セッションをまとめて集計します。

```bash
uv run codex-log-analysis --help
```

## 使い方

昨日ぶんのセッション概要を表示:

```bash
uv run codex-log-analysis report
```

特定日を指定:

```bash
uv run codex-log-analysis report --date 2025-11-03
```

ローカル Web UI を起動:

```bash
uv run codex-log-analysis serve --date 2026-03-28
```

起動後は `http://127.0.0.1:8765` を開くと、次の 2 タブを切り替えて見られます。

- セッション一覧
  通常セッションと archived セッションを小見出しで分けて表示し、各カードから「会話だけ」のセッション詳細ページへ移動
- Issue別要約
  issue 番号ごとに、関連セッション数、通常/archived 件数、関連タイトルを表示

全期間を上から 50 件だけ確認:

```bash
uv run codex-log-analysis report --all --limit 50
```

archived root や SQLite を明示したい場合:

```bash
uv run codex-log-analysis report \
  --date 2026-03-28 \
  --archived-root archived_sessions_snapshot \
  --sqlite state_5.sqlite
```

## 現在の出力

初期版では、ログから安定して取得できる次の事実を出します。

- SQLite 由来の `title`
- SQLite 由来の `git_branch`
- SQLite 由来の `archived` 状態
- `session_id`
- `cwd`
- 最初の実ユーザープロンプト
- 実ユーザープロンプト回数
- GitHub issue 参照らしき番号
- `skill` / `skill化` への言及回数
- キーワード上位
- JSONL ファイルパス

`archived_sessions_snapshot/` が存在すれば、archived されたセッションも既定でレポートに含みます。

## ファイル構成

- `AGENTS.md`: この repo での実装・検証ルール
- `.codex/napkin.md`: 再利用用の短い運用メモ
- `src/codex_log_analysis/cli.py`: セッション集計 CLI
