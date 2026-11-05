---
name: deploy
description: 健康診断を Fly.io の公開版へ反映する。テスト、デプロイ、公開URLでの確認まで行う。
disable-model-invocation: true
---
1. `.venv/Scripts/python -m unittest discover -s tests` が全部通ることを確かめる。落ちたら止まる
2. `git status` で未コミットが無いことを確かめる
3. `flyctl deploy --remote-only --ha=false` を実行する。`.env` はイメージに入らない（`.dockerignore`）
4. `flyctl status` でマシンが1台で `started` なことを確かめる。2台あれば回数の記録が分かれるので止まって知らせる
5. 公開URLで確かめる。Claudeを呼ばないので無料
   - `https://shindan.blanc.to/` が200
   - `/api/scan` へ `{"url":"http://169.254.169.254/"}` を送り400（内部アドレスを拒否）
6. デプロイで回数の記録が0に戻ることを報告に添える
