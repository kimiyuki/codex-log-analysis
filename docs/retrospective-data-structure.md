# Retrospective Data Structure

このメモは、Codex セッションの振り返りをする時に「今の JSONL と SQLite から何が取れるか」を整理したものです。

対象データは次の 3 系統です。

- `sessions_snapshot/`
  非 archived の rollout JSONL
- `archived_sessions_snapshot/`
  archived 済み rollout JSONL
- `state_*.sqlite`
  スレッド単位のメタデータと内部ログ

## 1. 結論

振り返り用の短い要約を作る時に、一番重要なのは次の役割分担です。

- JSONL
  会話本文、途中の commentary、tool call、最終回答、compact 後の置換履歴など「会話そのもの」
- SQLite `threads`
  `title`、`cwd`、`git_branch`、`archived`、`first_user_message` など「スレッドのメタデータ」
- SQLite `logs`
  websocket trace や内部イベントなど「低レベルの補助情報」

200〜300文字程度の要約を作るなら、主に使うべきなのは次です。

1. `threads.title`
2. `threads.first_user_message`
3. JSONL 中の `type=response_item` かつ `payload.type=message` の user / assistant
4. JSONL 中の `type=compacted` の `replacement_history`
5. 必要なら `event_msg.agent_message`

## 2. SQLite 側の構造

### 2.1 `threads` テーブル

`threads` はスレッド 1 件につき 1 行です。

主な列:

- `id`
  スレッド ID。JSONL の `session_meta.payload.id` と対応する
- `rollout_path`
  元 JSONL パス
- `created_at`, `updated_at`
  Unix epoch 秒
- `cwd`
  作業ディレクトリ
- `title`
  スレッドのタイトル。人間向け要約の出発点としてかなり有用
- `approval_mode`, `sandbox_policy`
  実行環境メタデータ
- `tokens_used`
  トークン使用量
- `archived`, `archived_at`
  archived 状態
- `git_sha`, `git_branch`, `git_origin_url`
  Git メタデータ
- `cli_version`, `source`, `model_provider`, `model`, `reasoning_effort`
  実行クライアントとモデル情報
- `first_user_message`
  最初の実ユーザーメッセージ。`title` と近いが、より生の依頼文に近い
- `agent_nickname`, `agent_role`, `agent_path`
  agent 実行時の補助メタデータ

振り返り要約に効く列:

- `title`
- `first_user_message`
- `cwd`
- `git_branch`
- `archived`
- `created_at`

### 2.2 `logs` テーブル

`logs` は内部ログです。

主な列:

- `ts`, `ts_nanos`
- `level`
- `target`
- `message`
- `thread_id`
- `process_uuid`

用途:

- websocket の送受信 trace
- `response.created` / `response.completed`
- `reasoning` の `encrypted_content`

振り返り要約への直接の有用性は低いです。可読な会話本文は基本的にここではなく JSONL 側にあります。

## 3. JSONL 側の構造

各 rollout JSONL は、時系列のイベント列です。1 行 1 JSON です。

トップレベルの `type` として、今回の手元データでは少なくとも次が見えています。

- `session_meta`
- `turn_context`
- `response_item`
- `event_msg`
- `compacted`

### 3.1 `session_meta`

セッション先頭に出るメタ情報です。

主な項目:

- `payload.id`
- `payload.timestamp`
- `payload.cwd`
- `payload.originator`
- `payload.cli_version`
- `payload.source`
- `payload.model_provider`
- 場合により `payload.instructions` または `payload.base_instructions`

用途:

- SQLite `threads.id` との結合キー
- セッション単位の基本情報確認

### 3.2 `turn_context`

ターンごとの文脈情報です。

主な項目:

- `payload.cwd`
- `payload.approval_policy`
- `payload.sandbox_policy`
- `payload.model`
- `payload.effort`
- `payload.summary`

用途:

- モデルや sandbox がターン途中で変わったかの確認
- 直接の会話要約にはあまり使わない

### 3.3 `response_item`

最重要です。会話本文や tool 実行がここに入ります。

`payload.type` の例:

- `message`
- `reasoning`
- `function_call`
- `function_call_output`
- `custom_tool_call`
- `custom_tool_call_output`
- `web_search_call`
- `ghost_snapshot`

特に重要なのは `payload.type=message` です。

#### `response_item.payload.type = message`

主な項目:

- `payload.role`
  `user` / `assistant` / `developer` など
- `payload.content`
  配列。`input_text` や `output_text` を持つ
- 場合により `payload.phase`
  `commentary` や `final_answer`

振り返り要約で使いやすいもの:

- `role=user`
  実際の依頼文
- `role=assistant` かつ `phase=final_answer`
  そのセッションの最終成果の要約として非常に使いやすい
- `role=assistant` かつ `phase=commentary`
  進行の途中経過が分かる

注意:

- 先頭には `<user_instructions>` や `<environment_context>`、`# AGENTS.md instructions ...` のようなメタ包みが入ることがある
- 人間向け要約ではこれらを除外した方がよい

#### `response_item.payload.type = reasoning`

主な項目:

- `summary`
  短い要約テキストが入る場合がある
- `encrypted_content`
  本文は暗号化されていて読めない

用途:

- 「何を考えていたか」のヒントにはなる
- 要約素材としては副次的

#### `function_call` / `function_call_output`

主な項目:

- 呼んだツール名
- 引数
- 出力

用途:

- 何を調べ、何を実行したかの証拠
- 200〜300字要約では「検証した」「Issue を更新した」程度に圧縮して使うのが現実的

### 3.4 `event_msg`

軽量な進行イベントです。

`payload.type` の例:

- `user_message`
- `agent_message`
- `agent_reasoning`
- `token_count`
- `task_started`
- `task_complete`
- `turn_aborted`
- `context_compacted`

振り返り要約で使いやすいもの:

- `user_message`
  user の依頼文の軽量版
- `agent_message`
  commentary の要点
- `task_started` / `task_complete`
  長い作業の切れ目

### 3.5 `compacted`

compact 後の置換履歴です。

主な項目:

- `payload.message`
- `payload.replacement_history`

`replacement_history` には、過去の `message` 群が縮約された形で入ることがあります。

重要な点:

- この `compacted` があれば、compact 前の会話の一部を平文で再利用できることがある
- ただし毎回同じ粒度とは限らない

## 4. 要約を作る時の観点

### 4.1 200〜300文字要約に向く項目

優先度順の候補:

1. `threads.title`
2. `threads.first_user_message`
3. assistant の `final_answer`
4. `compacted.replacement_history` 内の assistant 要約
5. user の最後の依頼
6. `cwd`, `git_branch`, `archived`

### 4.2 実用的な要約テンプレート

次の 4 要素が入ると、人間が振り返りやすいです。

- 何をしたか
  例: Issue #60 の対応方針整理、UI 修正、docs 再編
- 何を調べたか
  例: SQLite schema、PR コメント、GAS remote/local drift
- どこまで進んだか
  例: 実装済み、検証のみ、Issue コメントまで、設計相談で止めた
- 重要な結果
  例: archived セッションも SQLite で追える、save が publish を吸収する方針

### 4.3 要約素材として弱いもの

- `logs.message`
  低レベルすぎる
- `reasoning.encrypted_content`
  読めない
- `token_count`
  振り返りの本文には基本不要
- `sandbox_policy`
  特殊ケース以外は不要

## 5. いま言える構造上の整理

振り返り用途として見ると、実質的には次の 2 層構造です。

1. SQLite `threads`
   セッション見出しと索引を持つ
2. JSONL
   中身の本文と経過を持つ

このため、要約生成の基本戦略は次になります。

1. SQLite で対象スレッドを引く
2. `id` で JSONL を対応付ける
3. user / assistant message と `compacted` を優先して拾う
4. commentary や tool 実行は補助的に使う

## 6. 現時点の示唆

要約を本気で作るなら、`title` と `first_user_message` だけでは足りません。ただしそれだけでも「話題ラベル」としてはかなり強いです。

一方で、「どういう会話をしたか」を 200〜300文字で端的に出すなら、最も有力なのは次のどちらかです。

- assistant の `final_answer` を短く圧縮する
- `compacted.replacement_history` の assistant 要約を使う

つまり、今のデータ構造は「単なるログ」ではなく、「短い振り返りを書けるだけの材料はかなりある」という整理でよさそうです。
