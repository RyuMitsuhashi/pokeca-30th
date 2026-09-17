# SOUBADEX ｜ ポケカ相場

拡張パック「30th CELEBRATION」全165枠＋RGBミュウの図鑑と、主要30枚の価格推移（フリマ相場・カードラッシュ・DMMマイカ・店舗平均・買取）。
`collect.py` が各ECサイトの公開ページから直接価格を取り、`prices.json` に貯めてチャートと店舗別表に足していきます。

- `index.html` … ダッシュボード（一覧表・値動きトップ・詳細）（このファイルだけで動く）
- `collect.py` … DMMマイカの MEGA 期各弾の一覧から全カードの最安値、SAR以上と¥3,000以上のカードは店舗別出品まで取得。30th はカードラッシュ・晴れる屋2・トレカキャンプも。`sets.json`（弾とカード一覧）と `prices.json`（価格の履歴）を更新
- 弾が自動で見つからないときは DMM の一覧でその弾を選び、URL の `myca_primary_pack_id=` の数字を `collect.py` の `DMM_PACK_IDS` に追記（例 `"M2a": 6001`）
- `.github/workflows/fetch-prices.yml` … 毎日 9:00 / 21:00（JST）に自動実行してコミット
- `build_site.py` … SEO/AIO 用の静的ページ（sets/・cards/・og/・sitemap.xml・robots.txt・llms.txt）を収集のたびに生成
- `prices.json` / `ids.json` … 自動生成
- Figma デザイン（トークン・ダッシュボード・モーダル）: https://www.figma.com/design/WuF5P6zZ0i8qgcs0StOXov

## カード画像

TCGdex（https://tcgdex.dev/ ・ファン運営の非公式データベース）の API から M6a の画像URLを取り、一覧・カード帯・モーダルに表示します。ページ読み込み時に同一オリジンの `tcgdex-M6a.json`（Actions が毎回キャッシュ）→ 無ければ `api.tcgdex.net` の順で読みます。画像の権利は ©Pokémon/Nintendo/Creatures/GAME FREAK。非商用・個人利用の範囲で使ってください。TCGdex に画像が無いカードはプレースホルダーのままです。

## 自分の画像を使いたいとき

リポジトリに `img` フォルダを作り、`img/135.webp`（jpg・png でも可）のようにカード番号（3桁）をファイル名にして写真を置くだけで、一覧・カード帯・モーダルに表示されます（RGBミュウは `img/R.webp` など）。TCGdex の画像があるカードはそちらが優先されます。GitHub の「Add file → Upload files」に `img` フォルダごとドラッグすればまとめて上げられます。
