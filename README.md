# SOUBADEX ｜ ポケカ相場

拡張パック「30th CELEBRATION」全165枠＋RGBミュウの図鑑と、主要30枚の価格推移（フリマ相場・カードラッシュ・DMMマイカ・店舗平均・買取）。
`collect.py` が各ECサイトの公開ページから直接価格を取り、`prices.json` に貯めてチャートと店舗別表に足していきます。

- `index.html` … ダッシュボード（一覧表・値動きトップ・詳細）（このファイルだけで動く）
- `collect.py` … DMMマイカの MEGA 期各弾の一覧から全カードの最安値、SAR以上と¥3,000以上のカードは店舗別出品まで取得。30th はカードラッシュ・晴れる屋2・トレカキャンプも。`sets.json`（弾とカード一覧）と `prices.json`（価格の履歴）を更新
- 弾が自動で見つからないときは DMM の一覧でその弾を選び、URL の `myca_primary_pack_id=` の数字を `collect.py` の `DMM_PACK_IDS` に追記（例 `"M2a": 6001`）
- BOX の実勢価格は DMMマイカのポケモン一覧を `?keyword=BOX` で引いて取ります（`/items/box/<id>`）。各商品に付くシリーズコードのバッジ（M1L・M6a・sv9a など）でシリーズに紐づけるので、収集1回につきBOX一覧の読み込みも1回だけです。カートン・オリパ・ぷち抜き・パック単品は除外し、未開封（シュリンク付き）を優先。コードで当たらないシリーズだけ、そのシリーズ名でもう一度引きます
  確認は `python collect.py --boxes`（BOX商品の一覧とシリーズごとの採用結果をログに出して終了）
- BOX を確実に固定したいときは `collect.py` の `BOX_IDS` に商品IDを追記します。DMMマイカでそのBOXの商品ページを開き、URL 末尾の数字を書くだけ（例 `https://myca.dmm.com/pokemon-trading-card-game/items/box/10003970` → `"アビスアイ": 10003970,`）。キーはシリーズID（`"M6a"`）でも表示名の一部（`"アビスアイ"`）でも可。指定があれば一覧より優先してその商品ページを直接読みます。値を `0` にすると「そのシリーズのBOXは取得しない」＝DMMにまだBOXが無い弾で、名前の似た別商品（30th CELEBRATION に対する FUTURISTIC BOX など）を誤って拾わせないための指定です
- `.github/workflows/fetch-prices.yml` … 毎日 9:00 / 21:00（JST）に自動実行してコミット
- `build_site.py` … SEO/AIO 用の静的ページ（sets/・cards/・og/・sitemap.xml・robots.txt・llms.txt）を収集のたびに生成
- `prices.json` / `ids.json` … 自動生成
- Figma デザイン（トークン・ダッシュボード・モーダル）: https://www.figma.com/design/WuF5P6zZ0i8qgcs0StOXov

## カード画像

カード画像は自分で撮った写真だけを使います（外部の画像データベースは参照しません）。置き方は次のとおり。画像が無いカードは、カード名・番号・シリーズを記したプレースホルダー枠で表示されます。

## 自分の画像を使いたいとき

シリーズごとのフォルダに、カード番号（3桁）をファイル名にして置きます。**シリーズをまたいで番号が重なるので、フォルダ名（シリーズID）まで含めて決まります。**

```
img/
  M6a/135.webp     ← 30th CELEBRATION の 135/103
  M6a/R.webp       ← RGBミュウ（R/RGB は R）
  M1L/091.jpg      ← メガブレイブ の 091/063
```

- 拡張子は `webp` / `jpg` / `jpeg` / `png` のどれでも可（同じ番号に複数あれば webp を優先）。
- GitHub の「Add file → Upload files」に `M1L` フォルダごとドラッグすればまとめて上がります。
- 置いたあと収集（Actions）が1回走ると `tools/make_img_index.py` が `img/index.json`（画像の一覧）を作り直し、画面はそれを見て表示します。**手元で確認したいときは `python tools/make_img_index.py` を実行してください。**
- 昔の `img/135.webp`（直下置き）は 30th（M6a）の画像として引き続き使えます。
- 画像が無いカードはプレースホルダー（シリーズIDとカード名が入った枠）になります。
