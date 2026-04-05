# Markdown Note Export Follow-up

Date: 2026-04-05

## このセッションでやったこと

- `python -m codex_log_export export` を追加し、Codex の session log から Obsidian 向け Markdown を生成できる最小 CLI を作成した。
- 入力はまず実データで確認できた `rollout-*.jsonl` を主対象にしつつ、JSON 配列と `messages` / `records` / `items` / `events` のいずれか 1 つを持つ wrapper JSON に最低限対応した。
- `state_*.sqlite` を読むことで `title` / `cwd` / `branch` の補完を追加した。
- `sessions_snapshot/2026/04` を対象に `--mode note` で実生成し、`/tmp/codex-log-export-2026-04` に 30 件のノートを出力して確認した。

## 現在の方針

- ログ本体そのものは証拠として別に保持する。
- wiki 用のノートは raw log の転載ではなく、人間が短時間で読み返して意味が取れることを優先する。
- そのため exporter は現在 `note` モード前提とし、主に次を出す。
  - `Summary`
  - `Keywords`
  - `Key Phrases`
  - `Selected Messages`
  - `Tool Stats`
  - `Notes`

## 現状の違和感

- まだ「これでよい」と言えるノート品質には達していない。
- `Keywords` は日本語の語切りが素朴で、人が見て自然な語にならないことがある。
- `Key Phrases` もまだ機械的で、印象に残る文と設定文・定型文の分離が弱い。
- `Selected Messages` は現状だと `first user` / `first assistant` / `final assistant` 寄りで、セッションの山場をうまく拾えていない場合がある。
- automation 系の長い user prompt は、そのままだとノート先頭で重く感じる。

## 次に検討したいこと

1. `Keywords` を人間向けに改善する
   - 日本語の連続文字列をそのまま拾うのではなく、より自然な単位に寄せる。
   - 設定語や path 由来のノイズを減らす。

2. `Key Phrases` の選び方を改善する
   - 「重要そうな自然文」を優先し、command・identifier・frontmatter 的な文を落とす。
   - user の要求変化と assistant の結論をより強く拾う。

3. `Selected Messages` を再設計する
   - 先頭 / 終端だけでなく、中盤の方針転換や意思決定も候補に入れる。
   - 長すぎる user prompt は要約表示または抜粋表示を検討する。

4. ノートの最終レイアウトを再検討する
   - `Summary` を 3 行程度の要点に寄せる。
   - `Keywords` / `Key Phrases` / `Selected Messages` の順が本当に最適かを再確認する。

## 再実行コマンド

```bash
uv run python -m codex_log_export export \
  --input sessions_snapshot/2026/04 \
  --output /tmp/codex-log-export-2026-04 \
  --mode note \
  --overwrite \
  --sqlite state_5.sqlite
```

## 位置づけ

- この実装は「まず作って、実データで見て、違和感を特定する」ための最初の一歩。
- 次の作業は機能追加よりも、ノート品質の改善方針を詰めることが中心になる。
