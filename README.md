# おみせのホームページ健康診断

町の小さなお店の人が、自分のホームページのURLを入れると、外から見える範囲だけを調べて、次の3つを専門用語なしで返します。

- いま何が起きているか
- 放っておくと何が困るか
- 誰に何と頼めば直るか

業者に任せきりで、壊れても誰に何をどう頼めばいいか分からない。その壁を取り払うための道具です。

「Built with Claude: Japan 2026」の期間中（2026-11-02〜）に新しく作っています。

## 現在できること

URLを渡すと、次の項目を調べてJSONで出します。

- SSL証明書の期限と、httpからhttpsへの転送
- ドメインの期限（.jp を含む）
- トップページが開くか、画面にエラーの文字が出ていないか
- WordPressとPHPの古さ（外に版番号が出ている場合だけ）
- 検索に出ない設定（noindex・robots.txt）と title の有無
- スマホ向けの設定（viewport）
- メールの設定（MX・SPF・DMARC）
- お問い合わせフォームの送り先（HTMLを読むだけで、送信はしません）
- サイトとGoogleマップの電話番号の食い違い（`.env` に `SHINDAN_PLACES_API_KEY` があるときだけ）

`--explain` を付けると、Claude が調査結果を読み、急ぐ順の説明と依頼先ごとの依頼文を書きます。出力は調査結果と突合し、調査結果に無い数字・ドメイン名・項目を書いていたら差し戻します。

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m shindan.cli https://example.com
.venv\Scripts\python -m shindan.cli --explain https://example.com
```

画面で使うときは `.venv\Scripts\python -m shindan.web` を実行し、`http://127.0.0.1:8765/` を開きます。

`--explain` と画面の説明文には `.env` の `ANTHROPIC_API_KEY` を使います。

## 調べ方の約束

- 外から誰でも見られる情報だけを読みます。フォームの送信、ログイン画面への接触、脆弱性の探りはしません
- 社内ネットワークなど、公開されていないアドレスは読みに行きません
- 読み解きの文章は、調査結果に含まれる事実だけから作ります

## テスト

```
.venv\Scripts\python -m unittest discover -s tests
```
