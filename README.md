# 30th CELEBRATION 相場ダッシュボード

拡張パック「30th CELEBRATION」全165枠＋RGBミュウの図鑑と、主要30枚の価格推移（フリマ相場・カードラッシュ・DMMマイカ・店舗平均・買取）。
`collect.py` が各ECサイトの公開ページから直接価格を取り、`prices.json` に貯めてチャートと店舗別表に足していきます。

- `index.html` … ダッシュボード（一覧表・値動きトップ・詳細）（このファイルだけで動く）
- `collect.py` … DMMマイカ・カードラッシュ・晴れる屋2・トレカキャンプから価格を取得して `prices.json` に追記
- `.github/workflows/fetch-prices.yml` … 毎日 9:00 / 21:00（JST）に自動実行してコミット
- `prices.json` / `ids.json` … 自動生成
- Figma デザイン（トークン・ダッシュボード・モーダル）: https://www.figma.com/design/WuF5P6zZ0i8qgcs0StOXov

## カード画像

TCGdex（https://tcgdex.dev/ ・ファン運営の非公式データベース）の API から M6a の画像URLを取り、一覧・カード帯・モーダルに表示します。ページ読み込み時に同一オリジンの `tcgdex-M6a.json`（Actions が毎回キャッシュ）→ 無ければ `api.tcgdex.net` の順で読みます。画像の権利は ©Pokémon/Nintendo/Creatures/GAME FREAK。非商用・個人利用の範囲で使ってください。TCGdex に画像が無いカードはプレースホルダーのままです。

## 自分の画像を使いたいとき

`index.html` 内 `const FULL = [...]` の各行の7列目が画像URL欄です（例 `["135","ミュウex","FUR","6,000〜14,000円",374555,85240,"https://…/135.jpg"]`）。URLを入れると一覧・カード帯・モーダルに表示されます。

## GitHub での設定（10分、gitコマンド不要）

1. GitHub アカウントを作る → https://github.com/signup （既にあればスキップ）
2. 右上「+」→「New repository」。名前は `pokeca-30th` など。Public を選び「Create repository」
3. 「Add file」→「Upload files」に `index.html`・`collect.py`・`README.md` をドラッグして「Commit changes」
4. 「Add file」→「Create new file」。ファイル名欄に `.github/workflows/fetch-prices.yml` と入力し、同名ファイルの中身を貼って「Commit changes」
5. 「Settings」→「Actions」→「General」→ Workflow permissions を **Read and write permissions** にして Save
6. 「Actions」タブ → 左の「fetch-prices」→「Run workflow」で1回手動実行。1〜3分で `prices.json` がコミットされる
7. 「Settings」→「Pages」→ Source を **Deploy from a branch**、Branch を `main` / `/ (root)` にして Save
8. 数分後 `https://<ユーザー名>.github.io/pokeca-30th/` でダッシュボードが開き、以後は自動で点が増える

## 注意

- 各サイトの公開ページを読む個人用の仕組みです。メルカリ・ヤフオクは規約で自動取得が禁止のため対象外
- カードラッシュのページ構造は初回に `python collect.py --only cardrush --dump` で保存したHTMLを見て、必要なら `cardrush_page()` の正規表現を直す（`verify: true` が出た行は要確認）
- 商品IDが未確認のカードは `collect.py` の CARDS に追記する（商品ページURL末尾の数字／Shopifyは products/ の後ろ）
