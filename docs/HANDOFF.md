# openai-codex-mcp 申し送り — 2026-05-23 (完了)

## 現在の状態
Codex CLI を MCP ツール化する Python サーバー。codex CLI **v0.120.0** 対応が完了し、全コミットを自分の fork に push 済み。実バグなし。

## このプロジェクトについて
- サードパーティ `Tomatio13/openai-codex-mcp` の fork。279アプリ登録外（handoff-id なし・受信箱対象外）。
- リモート構成: `origin` = 自分の fork (`ytsukuda4470/openai-codex-mcp`) / `upstream` = 元リポ (`Tomatio13/...`)
- upstream 取り込み: `git fetch upstream && git merge upstream/main`

## 今セッションでやったこと
- WIP (`13fa543`) を検証 — `-o`(--output-last-message) ファイル出力・300秒タイムアウト・stdin閉じが v0.120.0 で正常動作することをスモークテストで確認
- `fa9be2d` codex_interactive の v0.120.0 移行漏れを修正。CLI フラグ組み立てを `_build_common_flags()` に共通化（run_codex と二重管理だったのが移行漏れの原因）。provider 設定キーを `provider` → `model_provider` に修正
- `9654683` .gitignore を Python 向けに整理（Next.js テンプレ流用エントリを削除）
- `run_codex` の死にコード `quiet` 引数を削除
- fork 作成 → 全コミット push

## 検証済みの事実（codex 0.120.0）
- `codex exec -o <file>` で最終メッセージをファイル取得できる
- デフォルトモデル `o4-mini` は有効
- `provider` 指定 → `-c model_provider="..."` が効く（banner で provider 反映を確認）
- 認証は API key (`sk-proj-...`) ログイン

## 次セッションでやること（任意・優先度低）
- 特になし。改善余地として: より新しいデフォルトモデル（gpt-5.1-codex 等）への変更検討、images 経路の実機検証

## ハマりポイント・注意事項
- `codex exec` と素の `codex`（対話）でフラグが共通。CLI 仕様変更時は `_build_common_flags()` 1箇所を直す
- v0.120.0 で廃止されたフラグ: `--quiet` / `--approval-mode` / `--provider`（→ それぞれ codex exec / --full-auto / -c model_provider= に移行済み）
- macOS に `timeout` コマンドなし。スモークテストは run_codex 内部の 300秒タイムアウト or Bash ツール側で
- `gh repo fork <repo>` に引数を渡すと `--remote` 系フラグは使えない（手動で remote 設定）

## 再開コマンド
cd ~/Projects/279/openai-codex-mcp && claude

## 関連リソース
- 本体: codex_server.py（run_codex / codex_agent / codex_interactive / _build_common_flags）
- fork: https://github.com/ytsukuda4470/openai-codex-mcp
- upstream: https://github.com/Tomatio13/openai-codex-mcp
