# Napkin Runbook

## Curation Rules
- Re-prioritize on every read.
- Keep recurring, high-value notes only.
- Max 10 items per category.
- Each item includes date + "Do instead".

## Execution & Validation (Highest Priority)
1. **[2026-03-29] 分析結果はログ由来の事実を優先**
   Do instead: JSONL に安定して存在する項目だけをレポートし、取れない情報は無理に推定しない。
2. **[2026-03-29] 軽量検証を毎回残す**
   Do instead: 実装後は `uv run` で CLI 実行確認と `compileall` を回して結果を報告する。

## Shell & Command Reliability
1. **[2026-03-29] サンプル確認は全件探索前に 1 ファイルから始める**
   Do instead: `find ... | head -n 1` と `sed` でログ形を確認してから集計処理を書く。

## Domain Behavior Guardrails
1. **[2026-03-29] `sessions_snapshot` は外部入力として扱う**
   Do instead: JSON parse failure や欠損フィールドは警告付きでスキップし、内部ロジックの整合性チェックとは分ける。
2. **[2026-03-29] branch や title は存在保証がない**
   Do instead: JSONL 単体では無理に推定せず、`state_*.sqlite` の `threads` を見て `title` や `git_branch` を補完する。
3. **[2026-03-29] archived セッションは主データとして扱う**
   Do instead: `sessions_snapshot/` だけでなく `archived_sessions_snapshot/` も既定で読み、SQLite の `archived` と突き合わせてレポートする。

## User Directives
1. **[2026-03-29] 初期環境は最小構成で作る**
   Do instead: `AGENTS.md`、`uv` 実行基盤、最小 CLI、README の使い方だけを先に整え、追加要件は後続で広げる。
