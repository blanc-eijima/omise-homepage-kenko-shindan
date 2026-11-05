# おみせのホームページ健康診断

## コマンド
- テスト: `.venv/Scripts/python -m unittest discover -s tests`（Claudeは呼ばない・無料）
- 手元の画面: `.venv/Scripts/python -m shindan.web`
- 公開: `/deploy`

## コードから読めない決定
- 公開リポジトリ。実在のお客様の名前・データ・認証情報を入れない。失敗例は架空のサイトで再現する
- 調べるのは外から誰でも見える範囲だけ。他人のサイトのフォームへ送信しない
- Googleのキーは専用の `SHINDAN_PLACES_API_KEY` だけを使う。共用のキーと取り違えない
- `ANTHROPIC_API_KEY` を手元の環境変数に置かない（Claude Code のログインより優先されてしまう）。`.env` か `fly secrets` に置く
- 回数の記録はメモリだけなので、fly.toml の `auto_stop_machines = "suspend"` を `stop` に変えない
- Claudeを呼ぶコマンドは費用がかかる。`--explain` と `evals/` は必要なときだけ動かす
