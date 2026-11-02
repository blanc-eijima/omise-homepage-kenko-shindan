# おみせのホームページ健康診断

町の小さなお店の人が、自分のホームページのURLを入れると、外から見える範囲だけを調べて、次の3つを専門用語なしで返します。

- いま何が起きているか
- 放っておくと何が困るか
- 誰に何と頼めば直るか

業者に任せきりで、壊れても誰に何をどう頼めばいいか分からない。その壁を取り払うための道具です。

「Built with Claude: Japan 2026」の期間中（2026-11-02〜）に新しく作っています。

## 現在できること

URLを渡すと、SSL証明書の状態、httpからhttpsへの転送、ドメインの期限を調べてJSONで出します。

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m shindan.cli https://example.com
```

## 調べ方の約束

- 外から誰でも見られる情報だけを読みます。フォームの送信、ログイン画面への接触、脆弱性の探りはしません
- 社内ネットワークなど、公開されていないアドレスは読みに行きません
- 読み解きの文章は、調査結果に含まれる事実だけから作ります

## テスト

```
.venv\Scripts\python -m unittest discover -s tests
```
