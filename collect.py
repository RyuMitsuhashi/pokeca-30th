#!/usr/bin/env python3
"""
ポケカ相場ダッシュボード データ収集 v2（複数弾対応）

やること
  1. DMMマイカの「ポケモンカードゲームMEGA」一覧から弾（パック）の一覧を見つける（見つからない弾は DMM_PACK_IDS に手で追記）
  2. 弾ごとに一覧ページをブラウザ描画で全ページ読み、全カードの「最安値・状態・レアリティ・商品ID」を取る → sets.json / prices.json
  3. SAR以上（HIGH_RARITY）または最安値が LISTING_MIN_PRICE 以上のカードは商品ページも開いて店舗別の出品一覧を取る
  4. 30th CELEBRATION（M6a）は従来どおりカードラッシュ・晴れる屋2・トレカキャンプも取る

使い方
  pip install requests beautifulsoup4 playwright && python -m playwright install chromium
  python collect.py                 # 全弾
  python collect.py --sets M6a,M2a  # 弾を絞る
  python collect.py --dump          # 取得したHTMLを ./dump/ に保存

注意：各サイトの公開ページを個人利用の範囲で読む前提。アクセスは控えめに（WAIT 秒間隔、1日2回）。
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, pathlib, re, sys, time
import requests
from bs4 import BeautifulSoup

WAIT = 2.0
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SOUBADEX-bot/2.0; +https://soubadex.com/#/about; contact@soubadex.com)", "Accept-Language": "ja,en;q=0.8"}
OUT = pathlib.Path("prices.json"); SETS_FILE = pathlib.Path("sets.json"); DUMP = pathlib.Path("dump")
JST = dt.timezone(dt.timedelta(hours=9))
BASE = "https://myca.dmm.com"; GENRE = "pokemon-trading-card-game"; SERIES = "ポケモンカードゲームMEGA"
DMM_ITEM = f"{BASE}/{GENRE}/items/single-card/{{id}}"
RUSH = "https://www.cardrush-pokemon.jp/product/{id}"
HARERUYA = "https://www.hareruya2.com/products/{id}.json"
CAMP = "https://torecacamp-pokemon.com/products/{id}.json"

# DMM のパックID。自動発見できなかった弾は、DMMの一覧でその弾を選んだときのURLの myca_primary_pack_id をここに書く
DMM_PACK_IDS = {"M6a": 6374, "M1L": 4761, "pack4762": 4762, "pack5250": 5250, "pack5873": 5873,
                "pack6011": 6011, "pack6124": 6124, "pack6244": 6244, "pack6621": 6621, "pack6390": 6390, "pack6389": 6389}   # 名前が無い分は一覧の見出しから読む
SET_NAMES = {"M6a": "30th CELEBRATION", "M1L": "メガブレイブ"}   # 表示名（自動発見した弾は DMM の表記が入る）
HIGH_RARITY = {"SAR", "FUR", "RGB", "SR", "UR", "ACE", "HR", "CSR", "CHR", "SSR", "MUR", "BWR"}
LISTING_MIN_PRICE = 3000   # この価格以上のカードも出品一覧まで取る
MAX_LIST_PAGES = 12

# 30th のカードラッシュ・Shopify 商品ID（従来どおり）
M6A_SHOPS = {
 "R/RGB": {"cardrush": 85241}, "G/RGB": {"cardrush": 85242}, "B/RGB": {"cardrush": 85243, "hareruya2": "10265831440704"},
 "135/103": {"cardrush": 85240, "hareruya2": "10265831145792", "torecacamp": "rc_it1a2gnsix5q_ecj6"},
 "134/103": {"cardrush": 85239, "torecacamp": "rc_it1qfx9a9xkk_opse"},
 "126/103": {"cardrush": 85231, "hareruya2": "10265832587584", "torecacamp": "rc_ituakuzx3s6w_djab"},
 "127/103": {"cardrush": 85232, "hareruya2": "10265831899456"}, "129/103": {"cardrush": 85234, "hareruya2": "10265831473472"},
 "131/103": {"cardrush": 85236, "hareruya2": "10265831342400"}, "128/103": {"cardrush": 85233, "hareruya2": "10265831964992"},
 "130/103": {"cardrush": 85235, "hareruya2": "10265831768384"}, "132/103": {"cardrush": 85237, "hareruya2": "10265831244096"},
 "125/103": {"cardrush": 85230, "hareruya2": "10265832358208"}, "133/103": {"cardrush": 85238, "hareruya2": "10265831407936"},
 "124/103": {"cardrush": 85229, "hareruya2": "10265835176256", "torecacamp": "rc_itexi5fvupgs_esux"},
 "142/103": {"cardrush": 85117, "hareruya2": "50719"}, "137/103": {"cardrush": 85112, "hareruya2": "10265836388672", "torecacamp": "rc_it9lhproroxw_voqr"},
 "165/103": {"cardrush": 85139, "hareruya2": "10265837830464", "torecacamp": "rc_itd2qz5fwkb4_0nek"},
 "150/103": {"cardrush": 85125, "hareruya2": "10265837568320"}, "136/103": {"cardrush": 85111, "hareruya2": "10265836814656", "torecacamp": "rc_itaoolmbea40_9bnm"},
 "141/103": {"cardrush": 85116, "hareruya2": "10265838092608"}, "151/103": {"cardrush": 85126, "hareruya2": "10265837994304"},
 "163/103": {"cardrush": 85137}, "160/103": {"cardrush": 85134}, "154/103": {"cardrush": 85128}, "156/103": {"cardrush": 85130},
 "162/103": {"cardrush": 85136}, "153/103": {"cardrush": 85127}, "138/103": {"cardrush": 85113}, "144/103": {"cardrush": 85119},
}

PRICE = re.compile(r"[¥￥]\s?([\d,]+)|([\d,]+)\s?円")
LINK = re.compile(r'href="(?:https://myca\.dmm\.com)?/' + GENRE + r'/items/single-card/(\d+)"[^>]*>(.*?)</a>', re.S)
CARDNO = re.compile(r"(\d{3}/\d{3}|[A-Z]/RGB)")


def yen(s): return int(str(s).replace(",", "")) if s else None
def log(msg): print(msg, file=sys.stderr, flush=True)


# ---------- 取得（requests / ブラウザ） ----------
def get(url, dump_name=None):
    r = requests.get(url, headers=HEADERS, timeout=30); r.raise_for_status()
    if dump_name: DUMP.mkdir(exist_ok=True); (DUMP / dump_name).write_text(r.text, encoding="utf-8")
    time.sleep(WAIT); return r.text


_B = {"pw": None, "browser": None}
def browser():
    if _B["browser"] is None:
        from playwright.sync_api import sync_playwright
        _B["pw"] = sync_playwright().start(); _B["browser"] = _B["pw"].chromium.launch()
    return _B["browser"]


def render(url, dump_name=None, js=None, wait_for=None, scroll=0, wait_ms=20000, settle_ms=1500):
    """JS描画後のHTML（js を渡せば page.evaluate の結果も）を返す。読み込み待ちは DOM 完成＋任意のセレクタ出現で判定"""
    page = browser().new_page(user_agent=HEADERS["User-Agent"], locale="ja-JP")
    try:
        try: page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e: log(f"  goto: {e.__class__.__name__}（取れた分で続行）")
        if wait_for:
            try: page.wait_for_selector(wait_for, timeout=wait_ms)
            except Exception: pass
        page.wait_for_timeout(settle_ms)
        for _ in range(scroll):   # 無限スクロール型の一覧を下まで読む
            page.mouse.wheel(0, 4000); page.wait_for_timeout(1200)
        html = page.content(); extra = page.evaluate(js) if js else None
    finally:
        page.close()
    if dump_name: DUMP.mkdir(exist_ok=True); (DUMP / dump_name).write_text(html, encoding="utf-8")
    time.sleep(WAIT)
    return (html, extra) if js else html


def close_browser():
    if _B["browser"]: _B["browser"].close()
    if _B["pw"]: _B["pw"].stop()


# ---------- DMM：弾の発見 ----------
PACK_JS = """() => { const out = {};
  document.querySelectorAll('a[href*="myca_primary_pack_id="]').forEach(a => { const m = a.href.match(/myca_primary_pack_id=(\\d+)/); const t = a.textContent.trim(); if (m && t && t.length < 60) out[t] = +m[1]; });
  document.querySelectorAll('option').forEach(o => { const s = o.closest('select'); const n = ((s && (s.name || s.id)) || '').toLowerCase(); if (/^\\d+$/.test(o.value) && o.textContent.trim() && n.includes('pack')) out[o.textContent.trim()] = +o.value; });
  document.querySelectorAll('input[type=checkbox],input[type=radio]').forEach(i => { if ((i.name || '').includes('pack') && /^\\d+$/.test(i.value)) { const l = i.closest('label') || (i.id && document.querySelector('label[for="' + i.id + '"]')); const t = l ? l.textContent.trim() : ''; if (t) out[t] = +i.value; } });
  return out; }"""


def discover_packs(dump) -> dict[str, int]:
    """DMM の一覧（MEGA）で絞り込み「封入パック」を開き、ページが受け取ったパック一覧のデータ（IDと名前）を通信とページ内容から拾う"""
    url = f"{BASE}/{GENRE}/list?cardseries={requests.utils.quote(SERIES)}"
    packs: dict[str, int] = {}
    blobs: list[str] = []
    page = browser().new_page(user_agent=HEADERS["User-Agent"], locale="ja-JP")
    def on_response(resp):
        try:
            ct = resp.headers.get("content-type", "")
            if "json" in ct or "text" in ct or "javascript" in ct:
                body = resp.text()
                if "pack" in body.lower() or "封入" in body: blobs.append(body)
        except Exception: pass
    page.on("response", on_response)
    try:
        try: page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception: pass
        page.wait_for_timeout(2500)
        try:
            page.get_by_text("封入パック", exact=True).first.click(); page.wait_for_timeout(1500)
            box = page.get_by_placeholder("封入パックを検索").first
            if box: box.fill(""); page.wait_for_timeout(800)
        except Exception as e:
            log(f"  封入パック: 開けず ({e.__class__.__name__})")
        blobs.append(page.content())
        if dump: DUMP.mkdir(exist_ok=True); (DUMP / "series_list.html").write_text(page.content(), encoding="utf-8")
    finally:
        page.close()
    # ID と名前の対を拾う（JSON でも RSC のペイロードでも、id と name が同じオブジェクト内に並ぶ）
    pat_a = re.compile(r'"(?:id|packId|pack_id|primary_pack_id|myca_primary_pack_id|value)"\s*:\s*"?(\d{2,6})"?[^{}]{0,200}?"(?:name|label|title|pack_name|packName)"\s*:\s*"((?:[^"\\]|\\.){2,60})"')
    pat_b = re.compile(r'"(?:name|label|title|pack_name|packName)"\s*:\s*"((?:[^"\\]|\\.){2,60})"[^{}]{0,200}?"(?:id|packId|pack_id|primary_pack_id|myca_primary_pack_id|value)"\s*:\s*"?(\d{2,6})"?')
    for b in blobs:
        for m in pat_a.finditer(b): packs.setdefault(m.group(2).encode().decode("unicode_escape", "ignore") if "\\u" in m.group(2) else m.group(2), int(m.group(1)))
        for m in pat_b.finditer(b): packs.setdefault(m.group(1).encode().decode("unicode_escape", "ignore") if "\\u" in m.group(1) else m.group(1), int(m.group(2)))
    # パックらしい名前だけ残す（拡張パック・ハイクラスパック・デッキ・BOX・プロモ など）
    keep = {n: i for n, i in packs.items() if re.search(r"パック|デッキ|BOX|ボックス|セット|プロモ|コレクション|ex|ex|30th", n)}
    log(f"dmm packs found: {len(keep)}（候補{len(packs)}） → {list(keep.items())[:15]}")
    return keep


PACKS_FILE = pathlib.Path("packs.json")   # 総当たりで見つけたパックIDのキャッシュ {setId: {name, pack_id}}

def probe_packs(center: int = 6374, before: int = 140, after: int = 30) -> dict[str, dict]:
    """絞り込みUIが読めないときの保険：pack id を前後に総当たりして、一覧の『…/M6a』からシリーズを判定する（1回だけ、結果はキャッシュ）"""
    found = json.loads(PACKS_FILE.read_text(encoding="utf-8")) if PACKS_FILE.exists() else {}
    if found: return found
    base = f"{BASE}/{GENRE}/list?cardseries={requests.utils.quote(SERIES)}&myca_primary_pack_id="
    ids = list(range(center - 1, center - before - 1, -1)) + list(range(center + 1, center + after + 1))
    for n, pid in enumerate(ids, 1):
        if n % 10 == 0: log(f"  probe 進行 {n}/{len(ids)}（見つかった: {len(found)}）")
        try:
            html = render(base + str(pid), None, wait_for='a[href*="/items/single-card/"]', wait_ms=5000, settle_ms=300)
        except Exception as e:
            log(f"  probe {pid}: {e}"); continue
        cards = parse_list(html)
        codes = [c["setcode"] for c in cards if c["setcode"]]
        if not codes: continue
        code = max(set(codes), key=codes.count)
        if not code.lower().startswith("m") or code in found: continue
        m = re.search(r"<title>(.*?)</title>", html, re.S); title = re.sub(r"\s*[|｜].*$", "", m.group(1)).strip() if m else code
        found[code] = {"name": title or code, "pack_id": pid}
        log(f"  probe {pid}: {code} {found[code]['name']} ({len(cards)}枚)")
    PACKS_FILE.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    return found


# ---------- DMM：一覧ページから全カード ----------
def parse_list(html: str) -> list[dict]:
    """一覧ページ → [{key, no, name, rarity, setcode, dmmId, lowest, cond}]"""
    out, seen = [], set()
    links = list(LINK.finditer(html))
    for i, m in enumerate(links):
        cid = int(m.group(1)); name = BeautifulSoup(m.group(2), "html.parser").get_text(" ", strip=True)
        if not name or cid in seen: continue
        seg = html[m.end(): links[i + 1].start() if i + 1 < len(links) else m.end() + 3000]
        text = BeautifulSoup(seg, "html.parser").get_text("\n", strip=True)
        meta = re.search(r"(\d{3}/\d{3}|[A-Z]/RGB)/([A-Za-z]+)/([A-Za-z0-9]+)", text)
        if meta:   # 30th 型：135/103/FUR/M6a が1行
            key, rarity, setcode = meta.group(1), meta.group(2).upper(), meta.group(3)
        else:      # MEGA 型：名前に「091/063」、別行に「SAR/M1L」
            k = CARDNO.search(name) or CARDNO.search(text); key = k.group(1) if k else None
            rc = re.search(r"(?:^|\n)\s*([A-Z]{1,4}|[A-Z]{1,3}\d?)/([A-Za-z]{1,3}\d[A-Za-z0-9]{0,3})\s*(?:\n|$)", text)
            rarity, setcode = (rc.group(1).upper(), rc.group(2)) if rc else ("", "")
        if not key: continue
        p = PRICE.search(text); c = re.search(r"状態([A-Z][+\-]?)", text)
        grade = "psa10" if re.search(r"PSA\s*10", name + " " + text, re.I) else ("psa9" if re.search(r"PSA\s*9\b", name + " " + text, re.I) else "raw")
        seen.add(cid)
        out.append({"key": key, "no": key.split("/")[0], "name": re.sub(r"\s*" + re.escape(key) + r"\s*", "", name).strip() or name,
                    "rarity": rarity, "setcode": setcode, "dmmId": cid, "lowest": yen(p.group(1) or p.group(2)) if p else None, "cond": c.group(1) if c else None, "grade": grade})
    return out


# ---------- DMM：BOX（未開封）の販売価格 ----------
# BOX は単品カードとは別カテゴリ（/items/box/<id>）。ポケモンの一覧を keyword=BOX で引くと
# 全シリーズのBOXが一度に並び、各商品にシリーズコード（M1L / M6a / sv9a …）のバッジが付く。
# そのコードでシリーズに紐づけるので、シリーズごとに検索し直す必要がない。
BOX_LIST = BASE + "/" + GENRE + "/list?keyword={kw}"
ITEM_LINK = re.compile(r'<a\b[^>]*href="([^"]*/items/([a-z0-9-]+)/(\d+))"[^>]*>(.*?)</a>', re.S)
BOX_WORD = re.compile(r"BOX|ＢＯＸ|ボックス", re.I)
BOX_NG = re.compile(r"カートン|オリパ|ぷち抜き|福袋|くじ|1パック|１パック|パック単品|バラ売り|開封済|開封品|中身|スリーブ|デッキケース|プレイマット|収納|ストレージ|ローダー")
BOX_UNSEALED = re.compile(r"シュリンクなし|シュリンク無|シュリンク剥がし|未シュリンク")
BOX_SEALED = re.compile(r"未開封|未使用品|シュリンク付")
SETCODE = re.compile(r"^(M\d{1,2}[A-Za-z]?|sv\d{1,2}[A-Za-z]?|SV\d[A-Za-z]?)$")   # バッジのシリーズコード
BOX_MIN_PRICE = 2000; BOX_MAX_PRICE = 300000; MAX_BOX_PAGES = 8
DMM_BOX_ITEM = BASE + "/" + GENRE + "/items/box/{id}"

# BOX の商品IDを手で指定したいとき（DMMマイカでそのBOXの商品ページを開き、URL 末尾の数字を書く）。
# キーはシリーズID（M6a など）。シリーズIDが分からないときは表示名の一部でも可（例 "アビスアイ"）。
# 指定があれば keyword=BOX の一覧より優先して、その商品ページを直接読む。
# 値を 0 にすると「このシリーズのBOXは取得しない」。DMMにまだBOXが無い弾で、名前が似た別商品
#（例：30th CELEBRATION に対する FUTURISTIC BOX）を誤って拾わないようにするために使う。
BOX_IDS: dict[str, int] = {
    # --- MEGA期（シリーズIDをキーにする。サイトの表示で確認済み）---
    "M1L": 10003850,   # メガブレイブ BOX
    "M1S": 10003860,   # メガシンフォニア BOX
    "M2":  10003880,   # インフェルノX BOX
    "M2a": 10003900,   # MEGAドリームex BOX
    "M3":  10003925,   # ムニキスゼロ BOX
    "M4":  10003950,   # ニンジャスピナー BOX
    "M5":  10003970,   # アビスアイ BOX
    "M6":  10003980,   # ストームエメラルダ BOX
    "M6a": 10004030,   # 30th CELEBRATION BOX（10004020 は別商品の FUTURISTIC BOX なので使わない）
    "30th CELEBRATION": 0,   # プレミアムデッキセット等、30th系の別商品には BOX を付けない（0 = 取得しない）
    # --- スカーレット＆バイオレット期 ---
    "熱風のアリーナ":         10003760,   # sv9a
    "テラスタルフェスex":      10003730,   # sv8a
    "ポケモンカード151":      10003375,   # sv2a
    "楽園ドラゴーナ":         10003660,   # sv7a
    "スカーレットex":         10003285,   # SV1S
    "ホワイトフレア":         10003810,
    "ブラックボルト":         10003800,
    "ロケット団の栄光":       10003775,
    "バトルパートナーズ":      10003740,
    "超電ブレイカー":         10003670,
    "ステラミラクル":         10003640,
    "ナイトワンダラー":       10003625,
    "変幻の仮面":            10003600,
    "クリムゾンヘイズ":       10003575,
    "サイバージャッジ":       10003545,
    "ワイルドフォース":       10003535,
    "シャイニートレジャーex":   10003525,
    "未来の一閃":            10003490,
    "古代の咆哮":            10003480,
    "レイジングサーフ":       10003455,
    # --- シリーズに紐づかない商品（実勢価格には使わない。番号の控え）---
    # 10004020 30th CELEBRATION FUTURISTIC BOX / 10003765 ロケット団の栄光 アタッシュケースセット
    # 10003820 スペシャルBOX ポケモンセンターヒロシマ / 10003815 トウホク / 10003825 フクオカ
}


BOX_COND = re.compile(r"^(未使用品|未開封|シュリンク付き?|状態[A-Z][+\-]?|プレイ用|傷あり)$")
BOX_NOISE = re.compile(r"送料|以上の注文|クーポン|ポイント|セール|値下げ")


def strip_sales(text: str) -> str:
    """本文から販売履歴の行を取り除く（合計金額を商品価格と取り違えないため）。
    見出しが変わっても壊れないよう、履歴らしい行が続く間だけを落とす"""
    lines = text.split("\n"); out = []; in_hist = False
    for l in lines:
        t = l.strip()
        if t.startswith("販売履歴"): in_hist = True; continue
        if in_hist:
            parts = [x.strip() for x in t.split("\t") if x.strip()]   # 表がタブ区切りで1行に来ることがある
            head = parts[0] if parts else ""
            if (not parts or head in ("販売日", "状態", "枚数", "価格") or SALES_WHEN.match(head)
                    or SALES_QTY.match(head) or SALES_PRICE.match(head) or BOX_COND.match(head) or head == "未使用"): continue
            in_hist = False
        out.append(l)
    return "\n".join(out)


def box_listings(html: str) -> list[dict]:
    """BOX の『他の出品情報』→ [{shop, price, cond}]。単品カードと違い状態が『未使用品』なので別扱い"""
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    i = text.find("他の出品情報")
    if i < 0: return []
    sec = text[i:]
    j = sec.find("関連カード")
    if j > 0: sec = sec[:j]
    lines = [l.strip() for l in sec.split("\n") if l.strip()]
    skip = ("他の出品情報", "状態が良い順", "状態について", "カートに追加", "ほしいものリストに追加", "全")
    out = []
    for k, l in enumerate(lines):
        m = re.match(r"^[¥￥]\s?([\d,]+)$", l)
        if not m: continue
        v = yen(m.group(1))
        if not v or not (BOX_MIN_PRICE <= v <= BOX_MAX_PRICE): continue
        shop = next((lines[b] for b in range(k - 1, max(-1, k - 4), -1)
                     if not lines[b].startswith(skip) and not BOX_NOISE.search(lines[b])
                     and not re.match(r"^[¥￥\d]", lines[b]) and not BOX_COND.match(lines[b])), None)
        cond = next((lines[f] for f in range(k + 1, min(len(lines), k + 4)) if BOX_COND.match(lines[f])), None)
        out.append({"shop": shop, "price": v, "cond": cond})
    return out


def dmm_box_item(cid: int, dump: bool) -> dict | None:
    """BOX の商品ページを直接読む（手動指定用）。出品一覧があればその最安を採る"""
    try:
        html = render(DMM_BOX_ITEM.format(id=cid), f"box_item_{cid}.html" if dump else None, wait_ms=20000, settle_ms=800)
    except Exception as e:
        log(f"  BOX商品 {cid}: {e}"); return None
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    t = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    name = BeautifulSoup(t.group(1), "html.parser").get_text(" ", strip=True) if t else ""
    if not name:
        t = re.search(r"<title>(.*?)</title>", html, re.S)
        name = re.sub(r"\s*[|｜].*$", "", t.group(1)).strip() if t else str(cid)
    ls = box_listings(html)   # BOX の出品は状態表記が「未使用品」なので専用に読む
    price = min((l["price"] for l in ls), default=None)
    if not price:   # 出品一覧が読めないときだけ、販売履歴を除いた本文の最初の価格を採る
        price = next((v for v in (yen(m.group(1) or m.group(2)) for m in PRICE.finditer(strip_sales(text)))
                      if v and BOX_MIN_PRICE <= v <= BOX_MAX_PRICE), None)
    if not price: log(f"  BOX商品 {cid}『{name}』: 価格が読めず"); return None
    code = next((l for l in (x.strip() for x in text.split("\n")) if SETCODE.match(l)), "")
    sold = sales_summary(parse_sales(html))   # BOX も販売履歴（実際に売れた価格・個数）を持つ
    return {"name": name, "dmmId": cid, "setcode": code, "lowest": price, "sold": sold,
            "sealed": bool(BOX_SEALED.search(text)) and not BOX_UNSEALED.search(name),
            "url": DMM_BOX_ITEM.format(id=cid), "listings": len(ls)}


def box_id_for(set_id: str, series_name: str) -> int | None:
    """BOX_IDS からこのシリーズの商品IDを引く（シリーズID → 表示名の部分一致の順）"""
    if set_id in BOX_IDS: return BOX_IDS[set_id]
    nm = (series_name or "").replace(" ", "")
    hits = [(k, v) for k, v in BOX_IDS.items() if k.replace(" ", "") and k.replace(" ", "") in nm]
    return max(hits, key=lambda kv: len(kv[0]))[1] if hits else None   # 一番長く一致するキーを採る


def parse_boxes(html: str) -> list[dict]:
    """一覧HTML → BOX商品 [{name, dmmId, setcode, lowest, sealed, url}]"""
    out, seen = [], set()
    links = list(ITEM_LINK.finditer(html))
    for i, m in enumerate(links):
        href, kind, cid = m.group(1), m.group(2), int(m.group(3))
        name = BeautifulSoup(m.group(4), "html.parser").get_text(" ", strip=True)
        if not name or cid in seen: continue
        if kind != "box" and not BOX_WORD.search(name): continue
        if CARDNO.search(name): continue                      # カード番号があれば単品カード
        end = min(links[i + 1].start(), m.end() + 1500) if i + 1 < len(links) else m.end() + 1500
        text = BeautifulSoup(html[m.end():end], "html.parser").get_text("\n", strip=True)
        blob = name + "\n" + text
        if BOX_NG.search(blob): continue
        pm = PRICE.search(name) or PRICE.search(text)
        price = yen(pm.group(1) or pm.group(2)) if pm else None
        if not price or not (BOX_MIN_PRICE <= price <= BOX_MAX_PRICE): continue
        code = next((l for l in (x.strip() for x in text.split("\n")) if SETCODE.match(l)), "")
        seen.add(cid)
        out.append({"name": name, "dmmId": cid, "setcode": code, "lowest": price,
                    "sealed": bool(BOX_SEALED.search(blob)) and not BOX_UNSEALED.search(blob),
                    "url": href if href.startswith("http") else BASE + href})
    return out


def box_query(series_name: str) -> str:
    """『拡張パック メガブレイブ』→『メガブレイブ』（名前で照合するとき用に接頭辞を落とす）"""
    return re.sub(r"^(拡張パック|強化拡張パック|ハイクラスパック|スペシャルセット)\s*", "", series_name or "").strip()


def pick_box(boxes: list[dict], set_id: str = "", series_name: str = "") -> dict | None:
    """シリーズコードが一致するものを最優先、次に名前一致。どちらもシュリンク付き→最安の順"""
    if not boxes: return None
    code = (set_id or "").lower()
    q = box_query(series_name).replace(" ", "")
    by_code = [b for b in boxes if code and (b.get("setcode") or "").lower() == code]
    by_name = [b for b in boxes if q and q in b["name"].replace(" ", "")]
    for pool in ([b for b in by_code if b["sealed"]], by_code, [b for b in by_name if b["sealed"]], by_name):
        if pool: return min(pool, key=lambda b: b["lowest"])
    return None


def dmm_box_index(dump: bool, keyword: str = "BOX") -> list[dict]:
    """ポケモン一覧を keyword で引いて、全シリーズのBOX商品を一度に集める"""
    found: list[dict] = []
    for page in range(1, MAX_BOX_PAGES + 1):
        url = BOX_LIST.format(kw=requests.utils.quote(keyword)) + (f"&page={page}" if page > 1 else "")
        try:
            html = render(url, f"boxlist_{keyword}_p{page}.html" if dump else None, wait_for='a[href*="/items/"]', scroll=3)
        except Exception as e:
            log(f"  BOX一覧 p{page}: {e}"); break
        ids = {b["dmmId"] for b in found}
        got = [b for b in parse_boxes(html) if b["dmmId"] not in ids]
        found += got
        log(f"  BOX一覧『{keyword}』p{page}: +{len(got)}件（計{len(found)}）")
        if not got: break
    return found


PAGE_TITLE = {}   # pack_id → 一覧の見出し（パック名）

def collect_set_list(pack_id: int, dump: bool, tag: str) -> list[dict]:
    cards, seen = [], set()
    base = f"{BASE}/{GENRE}/list?cardseries={requests.utils.quote(SERIES)}&myca_primary_pack_id={pack_id}"
    for page in range(1, MAX_LIST_PAGES + 1):
        html = ""
        for attempt in range(2):
            try:
                html = render(f"{base}&page={page}", f"list_{tag}_p{page}.html" if dump else None, wait_for='a[href*="/items/single-card/"]', scroll=3); break
            except Exception as e:
                log(f"  list page {page} attempt {attempt+1} failed: {e}")
        if not html: break
        if page == 1:
            m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
            if m: PAGE_TITLE[pack_id] = BeautifulSoup(m.group(1), "html.parser").get_text(" ", strip=True)
        found = [c for c in parse_list(html) if c["dmmId"] not in seen]
        for c in found: seen.add(c["dmmId"])
        cards += found
        log(f"  {tag} page {page}: {len(found)} new cards")
        if not found: break
    return cards


# ---------- DMM：商品ページ（出品一覧） ----------
def parse_listings(html: str) -> list[dict]:
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    i = text.find("他の出品情報"); sec = text[i:] if i >= 0 else text
    j = sec.find("関連カード"); sec = sec[:j] if j > 0 else sec
    lines = [l.strip() for l in sec.split("\n") if l.strip()]
    skip = ("SALE中", "お買い得", "状態", "他の出品情報", "在庫", "残り", "カートに入れる")
    out = []
    for k, l in enumerate(lines):
        m = re.match(r"[¥￥]\s?([\d,]+)", l)
        if not m: continue
        shop = next((lines[b] for b in range(k - 1, max(-1, k - 4), -1) if not lines[b].startswith(skip) and not re.match(r"[¥￥]", lines[b])), None)
        cond = None
        for f in range(k + 1, min(len(lines), k + 5)):
            c = re.match(r"状態([A-Z][+\-]?)", lines[f])
            if c: cond = c.group(1); break
            if re.match(r"[¥￥]", lines[f]): break
        if shop and cond: out.append({"shop": shop, "price": yen(m.group(1)), "cond": cond})
    return out


# ---------- DMM：商品ページ（販売履歴＝実際に売れた価格と枚数） ----------
# 例）『2時間前 / 未使用 / 25個 / ¥475,000』『2026/08/25 / 状態A / 1枚 / ¥250』
# 価格は合計なので、枚数で割って1枚あたりの成約単価にする。
SALES_WHEN = re.compile(r"^(?:(\d{4})[/-](\d{1,2})[/-](\d{1,2})|(?:約)?\s*(\d+)\s*(分|時間|日|週間|週|か月|ヶ月|カ月|年)前|たった今|今)$")
SALES_QTY = re.compile(r"^(\d+)\s*[個枚]$")
SALES_PRICE = re.compile(r"^[¥￥]\s?([\d,]+)$")
DELTA = {"分": 1 / 1440, "時間": 1 / 24, "日": 1, "週間": 7, "週": 7, "か月": 30, "ヶ月": 30, "カ月": 30, "年": 365}


def _sales_when(m, now: dt.datetime) -> str:
    if m.group(1): return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    if m.group(4): return (now - dt.timedelta(days=int(m.group(4)) * DELTA.get(m.group(5), 1))).strftime("%Y-%m-%d")
    return now.strftime("%Y-%m-%d")


def parse_sales(html: str) -> list[dict]:
    """商品ページ → 販売履歴 [{when, cond, qty, total, unit}]（新しい順）"""
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    i = text.find("販売履歴")
    if i < 0: return []
    sec = text[i:]
    for stop in ("他の出品情報", "関連カード"):
        j = sec.find(stop)
        if j > 0: sec = sec[:j]
    now = dt.datetime.now(JST)
    out, cur = [], {}
    for raw in sec.split("\n"):
        for l in [x.strip() for x in raw.split("\t")]:   # 表がタブ区切りで来ることがある
            if not l or l in ("販売履歴", "販売日", "状態", "枚数", "価格"): continue
            w = SALES_WHEN.match(l)
            if w: cur = {"when": _sales_when(w, now)}; continue
            if not cur: continue
            q = SALES_QTY.match(l)
            if q: cur["qty"] = int(q.group(1)); continue
            pm = SALES_PRICE.match(l)
            if pm and cur.get("qty"):
                total = yen(pm.group(1))
                if total: out.append({**cur, "total": total, "unit": int(round(total / cur["qty"]))})
                cur = {}; continue
            cur.setdefault("cond", l)
    return out


def sales_summary(sales: list[dict], days: int = 30) -> dict | None:
    """販売履歴 → {med(中央値), last(直近単価), n(件数), qty(枚数), when(最新日)}"""
    if not sales: return None
    lim = (dt.datetime.now(JST) - dt.timedelta(days=days)).strftime("%Y-%m-%d")
    rows = [r for r in sales if r["when"] >= lim] or sales
    # 中央値は「枚数で重み付け」する。1枚だけの取引と43枚まとめ買いを同じ1票にしない
    qty = sum(r["qty"] for r in rows)
    med, seen = rows[0]["unit"], 0
    for r in sorted(rows, key=lambda x: x["unit"]):
        seen += r["qty"]
        if seen >= qty / 2: med = r["unit"]; break
    return {"med": med, "last": rows[0]["unit"], "n": len(rows), "qty": qty, "when": rows[0]["when"]}


def dmm_item(cid: int, dump: bool) -> dict:
    """商品ページを1回読んで、出品一覧と販売履歴の両方を返す（リクエストは増やさない）"""
    try:
        html = render(DMM_ITEM.format(id=cid), f"dmm_{cid}.html" if dump else None, wait_for="text=他の出品情報")
    except Exception as e:
        log(f"  dmm item {cid} failed: {e}"); return {"listings": [], "sold": None}
    return {"listings": parse_listings(html), "sold": sales_summary(parse_sales(html))}


# ---------- 30th の他店 ----------
def cardrush_page(pid, dump):
    html = get(RUSH.format(id=pid), f"cardrush_{pid}.html" if dump else None)
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    def near(label):
        i = text.find(label)
        if i < 0: return None
        m = PRICE.search(text[i:i + 300]); return yen(m.group(1) or m.group(2)) if m else None
    sell = near("販売価格") or near("価格"); buy = near("買取価格")
    soldout = ("再入荷を知らせる" in text and "カートに入れる" not in text) or bool(re.search(r"sold\s*out|売り切れ|在庫切れ", text, re.I))
    return {"sell": sell, "buy": buy, "soldout": soldout}


def shopify_json(url, dump_name, dump):
    try: txt = get(url, dump_name if dump else None)
    except requests.RequestException: time.sleep(5); txt = get(url, dump_name if dump else None)
    p = json.loads(txt)["product"]
    vs = [v for v in p.get("variants", []) if v.get("available", True)] or p.get("variants", [])
    price = min((float(v["price"]) for v in vs if v.get("price")), default=None)
    if price and price > 1_000_000 and float(vs[0]["price"]) % 100 == 0: price = price / 100
    return {"sell": int(price) if price else None}


# ---------- 買取価格（第1段：Web上のテキスト価格表） ----------
KANABELL_BUY_URL = ""   # カーナベルの買取検索URL（{q} にカード名）。ページ構造を確認してから入れる。空なら取得しない
BUY_OCR = pathlib.Path("buy_ocr.json")                      # ocr_buylist.py の出力（画像の買取表）

def parse_card_blocks(text: str) -> dict[str, int]:
    """行テキストから『カード番号 → 価格』を拾う汎用パーサ（番号の前後4行以内の『○○円』or『¥○○』）"""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    out = {}
    for i, l in enumerate(lines):
        m = CARDNO.search(l)
        if not m: continue
        for j in range(i, min(len(lines), i + 5)):
            p = re.search(r"[¥￥]\s?([\d,]+)|([\d,]+)\s?円", lines[j])
            if p:
                v = yen(p.group(1) or p.group(2))
                if v and v >= 10: out.setdefault(m.group(1), v); break
    return out


SHINSOKU_API = "https://shinsoku-tcg.com/api/items"   # 郵送買取（簡単カート買取）の一覧。画面と同じデータをJSONで返す
SHINSOKU_PAGES = 30          # 1ページ100件。ポケモンは約1,900件なので余裕をみて


def _norm(s: str) -> str:
    """カード名の表記ゆれを吸収（記号・空白・カッコ内を落とす）"""
    s = re.sub(r"[【\[（(].*?[】\])）]", "", str(s))
    return re.sub(r"[\s　・/\-‐−]", "", s).lower()


def shinsoku_buylist(dump: bool) -> dict[str, list[dict]]:
    """シンソクの郵送買取を API から取る → {カード番号: [{name, price, psa10, full}]}
    modelno に同じ番号で別カードが入っていることがあるので、番号だけでなく名前でも照合できるよう一覧で返す"""
    out: dict[str, list[dict]] = {}
    raw_all = []
    for page in range(SHINSOKU_PAGES):
        params = {"postal_only": "true", "sort": "price_desc", "type": "ALL", "brand": "ポケモン",
                  "page": page, "limit": 100}
        try:
            r = requests.get(SHINSOKU_API, params=params, headers=HEADERS, timeout=30)
            r.raise_for_status(); j = r.json()
        except Exception as e:
            log(f"  shinsoku p{page}: {e}"); break
        data = j.get("data") or {}
        items = data.get("items") or []
        raw_all += items
        for it in items:
            key_m = CARDNO.search(str(it.get("modelno") or ""))
            price = it.get("postal_purchase_price_s")
            if not key_m or not price: continue
            out.setdefault(key_m.group(1), []).append({
                "name": it.get("name") or "", "price": int(price),
                "psa10": any((t or {}).get("slug") == "psa10" for t in (it.get("tags") or [])),
                "full": bool(it.get("is_full_amount_flag"))})
        time.sleep(0.4)
        if not data.get("has_more") or not items: break
    if dump and raw_all:
        DUMP.mkdir(exist_ok=True); (DUMP / "shinsoku_items.json").write_text(json.dumps(raw_all, ensure_ascii=False, indent=1), encoding="utf-8")
    n_psa = sum(1 for v in out.values() for x in v if x["psa10"])
    log(f"  shinsoku: 商品 {len(raw_all)}件 → 番号つき {sum(len(v) for v in out.values())}件（PSA10 {n_psa}件 / 番号 {len(out)}種）")
    return out


def pick_shinsoku(entries: list[dict], card_name: str, psa10: bool) -> dict | None:
    """同じ番号の候補からこのカードのものを選ぶ。名前が一致するものを優先し、候補が1つだけなら採用"""
    cand = [e for e in entries if e["psa10"] == psa10]
    if not cand: return None
    n = _norm(card_name)
    hit = [e for e in cand if n and (n in _norm(e["name"]) or _norm(e["name"]) in n)]
    if hit: return max(hit, key=lambda e: e["price"])
    return cand[0] if len(cand) == 1 else None


def kanabell_buy(name: str, dump: bool) -> int | None:
    if not KANABELL_BUY_URL: return None
    try:
        text = BeautifulSoup(get(KANABELL_BUY_URL.format(q=requests.utils.quote(name))), "html.parser").get_text("\n", strip=True)
        vals = list(parse_card_blocks(text).values()); return max(vals) if vals else None
    except requests.RequestException: return None


def ocr_buy_by_key() -> dict[str, list[dict]]:
    """buy_ocr.json → {カード番号: [{shop, price, src, when, name}]}"""
    if not BUY_OCR.exists(): return {}
    out: dict[str, list[dict]] = {}
    for rec in json.loads(BUY_OCR.read_text(encoding="utf-8")):
        for row in rec.get("rows", []):
            k = row.get("no"); v = row.get("price")
            if k and v: out.setdefault(k, []).append({"shop": rec.get("shop"), "price": v, "src": rec.get("src"), "when": rec.get("date"), "name": row.get("name")})
    return out


# ---------- 店の通販サイトを検索して販売価格を読む（汎用） ----------
# base が空の店は取得しない。トレカラウンジは通販サイトのURLが分かったら入れる
# 販売価格を「通販サイトで検索して読む」店。シンソクは買取専門として扱うのでここには入れない（買取は shinsoku_buylist で取得）
SHOPS_SEARCH = {
    "torecalounge": {"label": "トレカラウンジ", "base": ""},   # 通販サイトのURLが分かったら入れる
}
SEARCH_RARITY = HIGH_RARITY   # 検索型は1枚ずつ開くので、SAR以上だけ

SEARCH_URL_PATTERNS = ["{base}product-list?keyword={q}", "{base}products/list?name={q}", "{base}search?keyword={q}", "{base}search?q={q}", "{base}?s={q}", "{base}products/search?q={q}"]
SHOP_STATE: dict[str, dict] = {}   # base → {"tmpl": 当たった検索URL, "fail": 連続失敗数, "off": True なら今回はやめる}

def _parse_hits(html: str, query: str) -> list[dict]:
    lines = [l.strip() for l in BeautifulSoup(html, "html.parser").get_text("\n", strip=True).split("\n") if l.strip()]
    hits = []
    for i, l in enumerate(lines):
        if query not in l: continue
        block = lines[max(0, i - 6): i + 7]
        prices = [yen(m.group(1) or m.group(2)) for m in (PRICE.search(x) for x in block) if m]
        prices = [v for v in prices if v and v >= 30]
        if not prices: continue
        sold = any(re.search(r"sold\s*out|売り切れ|在庫切れ|在庫なし", x, re.I) for x in block)
        psa = any(re.search(r"PSA\s*10", x, re.I) for x in block)
        hits.append({"sell": min(prices), "soldout": sold, "psa": psa})
    return hits


def _result(hits: list[dict], url: str) -> dict | None:
    if not hits: return None
    out = {"url": url}
    for grade, hs in (("raw", [h for h in hits if not h["psa"]]), ("psa10", [h for h in hits if h["psa"]])):
        if not hs: continue
        live = [h for h in hs if not h["soldout"]]; best = min(live or hs, key=lambda h: h["sell"])
        if grade == "raw": out["sell"] = best["sell"]; out["soldout"] = not live
        else: out["psa10"] = best["sell"]
    return out if ("sell" in out or "psa10" in out) else None


def shop_search_price(base: str, query: str, dump_name: str | None) -> dict | None:
    """通販サイトでカード番号を検索して販売価格を読む。検索欄が見えなければアイコンを押す→検索結果URLの型を総当たり。当たった型は記憶し、3連敗でその回は諦める"""
    st = SHOP_STATE.setdefault(base, {"tmpl": None, "fail": 0, "off": False})
    if st["off"]: return None
    from urllib.parse import quote
    def done(res):
        if res: st["fail"] = 0
        else:
            st["fail"] += 1
            if st["fail"] >= 3: st["off"] = True; log(f"  {base}: 3回続けて取れないので今回は販売価格をスキップ")
        return res
    # 1) 記憶した検索URL
    if st["tmpl"]:
        try:
            html = render(st["tmpl"].format(base=base, q=quote(query)), dump_name, wait_ms=8000, settle_ms=800)
            return done(_result(_parse_hits(html, query), st["tmpl"].format(base=base, q=quote(query))))
        except Exception as e:
            log(f"  search {query}: {e.__class__.__name__}"); return done(None)
    # 2) 検索欄（見えているもの）→ 無ければ検索アイコンを押してから
    page = browser().new_page(user_agent=HEADERS["User-Agent"], locale="ja-JP")
    try:
        try: page.goto(base, wait_until="domcontentloaded", timeout=60000)
        except Exception: pass
        page.wait_for_timeout(1500)
        sel = "input[type=search], input[name*=keyword], input[name*=search], input[name=q], input[name=s], input[placeholder*=検索]"
        def visible_input():
            for h in page.query_selector_all(sel):
                try:
                    if h.is_visible(): return h
                except Exception: pass
            return None
        inp = visible_input()
        if not inp:
            for tsel in ["button[aria-label*=検索]", "a[aria-label*=検索]", "[class*=search] button", "a[href*=search]", "[class*=search-toggle]", "[class*=btn-search]", "text=検索"]:
                try:
                    el = page.locator(tsel).first
                    if el and el.is_visible(): el.click(); page.wait_for_timeout(800); inp = visible_input()
                    if inp: break
                except Exception: pass
        if inp:
            inp.fill(query); inp.press("Enter")
            try: page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception: pass
            page.wait_for_timeout(1500)
            html = page.content(); url = page.url
            res = _result(_parse_hits(html, query), url)
            if res:
                m = re.search(r"([?&](?:keyword|q|s|name|search)=)", url)
                if m: st["tmpl"] = url.split(m.group(1))[0] + m.group(1) + "{q}"; st["tmpl"] = st["tmpl"].replace(base, "{base}", 1) if st["tmpl"].startswith(base) else st["tmpl"]
                return done(res)
    except Exception as e:
        log(f"  search {query}: {e.__class__.__name__}")
    finally:
        page.close()
    # 3) 検索結果URLの型を総当たり
    for tmpl in SEARCH_URL_PATTERNS:
        try:
            u = tmpl.format(base=base, q=quote(query))
            html = render(u, None, wait_ms=6000, settle_ms=600)
            res = _result(_parse_hits(html, query), u)
            if res: st["tmpl"] = tmpl; log(f"  {base}: 検索URLの型を記憶 {tmpl}"); return done(res)
        except Exception: pass
    return done(None)


# ---------- メイン ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="", help="弾IDをカンマ区切りで絞る（例 M6a,M2a）")
    ap.add_argument("--dump", action="store_true")
    ap.add_argument("--boxes", action="store_true", help="一覧のBOX行だけを確認して終了（--sets と併用推奨）")
    a = ap.parse_args()
    only = set(s.strip() for s in a.sets.split(",") if s.strip())

    packs = dict(DMM_PACK_IDS); names = dict(SET_NAMES)   # 手動指定 + 自動発見
    # 自動発見は全世代のパックを返すので、MEGA 期（ID が MIN_PACK_ID 以上）に絞り、一覧のカード表記が M で始まるものだけ採用。判定は packs.json に記憶
    MIN_PACK_ID = 4700; MAX_PROBE = 40
    cache = json.loads(PACKS_FILE.read_text(encoding="utf-8")) if PACKS_FILE.exists() else {}   # {pack_id: {"name", "code"}}
    discovered = [(n, pid) for n, pid in discover_packs(a.dump).items() if pid >= MIN_PACK_ID and pid not in packs.values()]
    probed = 0
    for name, pid in sorted(discovered, key=lambda x: x[1]):
        key = str(pid)
        if key not in cache:
            if probed >= MAX_PROBE: break
            probed += 1
            try:
                html = render(f"{BASE}/{GENRE}/list?cardseries={requests.utils.quote(SERIES)}&myca_primary_pack_id={pid}", None, wait_for='a[href*="/items/single-card/"]', wait_ms=6000, settle_ms=300)
                codes = [c["setcode"] for c in parse_list(html) if c["setcode"]]
                cache[key] = {"name": name, "code": max(set(codes), key=codes.count) if codes else ""}
            except Exception as e:
                cache[key] = {"name": name, "code": ""}
            log(f"  判定 {pid} {name} → {cache[key]['code'] or '対象外'}")
        code = cache[key].get("code", "")
        if re.match(r"^M\d", code) and code not in packs:
            packs[code] = pid; names[code] = name
    PACKS_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"対象パック: {len(packs)} → {[(k, v) for k, v in packs.items()]}")
    if len(packs) <= 1 and os.environ.get("PROBE_PACKS") == "1":   # 総当たりは環境変数で明示したときだけ
        for code, info in probe_packs().items():
            if info["pack_id"] in packs.values(): continue
            packs[code] = info["pack_id"]; names[code] = info["name"]
        log(f"packs after probe: {len(packs)} → {[(k, v) for k, v in packs.items()]}")
    if a.boxes:   # 確認用：BOX一覧だけ見て終わる
        idx = dmm_box_index(a.dump)
        log(f"BOX商品 {len(idx)}件（コード付き {sum(1 for b in idx if b['setcode'])}件）")
        for b in sorted(idx, key=lambda x: (x["setcode"] or "zz", x["lowest"])):
            log(f"  [{b['setcode'] or '—':>5}] ¥{b['lowest']:,}  {'封' if b['sealed'] else '?'}  {b['name']}  {b['url']}")
        log("--- シリーズごとの採用結果（BOX_IDS に貼れる形）---")
        for code, pid in packs.items():
            bid = box_id_for(code, names.get(code, ""))
            if bid is not None:
                log(f'    "{code}": {bid},   # BOX_IDS で指定済み' + ("（取得しない）" if bid == 0 else "")); continue
            pk = pick_box(idx, code, names.get(code, ""))
            if pk: log(f'    "{code}": {pk["dmmId"]},   # {pk["name"]} ¥{pk["lowest"]:,}')
            else:  log(f'    # "{code}": ?,   # {names.get(code, "")} … 見つからず（商品ページのURL末尾の数字を入れてください）')
        close_browser(); return

    sets_db = json.loads(SETS_FILE.read_text(encoding="utf-8")) if SETS_FILE.exists() else {}
    snap = {"fetched_at": dt.datetime.now(JST).isoformat(timespec="minutes"), "v": 2, "sets": {}}
    shinsoku = shinsoku_buylist(a.dump)        # 弾をまたぐ一覧なのでカード番号＋名前で照合
    box_index = dmm_box_index(a.dump)          # 全シリーズのBOXを1回で取る（シリーズコードで紐づけ）
    log(f"BOX商品: {len(box_index)}件（コード付き {sum(1 for b in box_index if b['setcode'])}件）")
    ocr = ocr_buy_by_key()

    for tmp_id, pid in packs.items():
        if only and tmp_id not in only and not (tmp_id.startswith("pack")): continue
        cards = collect_set_list(pid, a.dump, tmp_id)
        if not cards: log(f"{tmp_id}: カードなし（pack id {pid}）"); continue
        codes = [c["setcode"] for c in cards if c["setcode"]]
        set_id = max(set(codes), key=codes.count) if codes else tmp_id   # 『…/FUR/M6a』の末尾が弾ID
        if only and set_id not in only and tmp_id not in only: continue
        if tmp_id != set_id and tmp_id in sets_db: sets_db.pop(tmp_id)   # packXXXX で保存した古い項目を捨てる
        entry = sets_db.setdefault(set_id, {"id": set_id, "name": names.get(tmp_id, set_id), "dmm_pack_id": pid, "cards": {}})
        entry["dmm_pack_id"] = pid; entry["name"] = names.get(tmp_id) or PAGE_TITLE.get(pid) or entry.get("name") or set_id
        prices = {}
        graded = [c for c in cards if c.get("grade") in ("psa10", "psa9")]
        cards = [c for c in cards if c.get("grade", "raw") == "raw"]
        for g in graded:   # 鑑定品：同じ番号の素体カードに psa10/psa9 として付ける
            if g["grade"] != "psa10": continue
            P = {"lowest": g["lowest"], "dmmId": g["dmmId"]}
            if g["rarity"] in HIGH_RARITY or (g["lowest"] or 0) >= LISTING_MIN_PRICE:
                it = dmm_item(g["dmmId"], a.dump); ls = it["listings"]
                if ls: low = min(ls, key=lambda l: l["price"]); P = {"lowest": low["price"], "dmmId": g["dmmId"], "listings": ls}
                if it["sold"]: P["sold"] = it["sold"]
            prices.setdefault(g["key"], {"prices": {}})["prices"]["psa10"] = P
        for c in cards:
            entry["cards"][c["key"]] = {"no": c["no"], "name": c["name"], "rarity": c["rarity"], "dmmId": c["dmmId"]}
            P = prices.get(c["key"], {}).get("prices", {}); P["dmm"] = {"lowest": c["lowest"], "cond": c["cond"]}
            buy = {}
            sh = shinsoku.get(c["key"], [])
            hit = pick_shinsoku(sh, c["name"], psa10=False)
            if hit: buy["shinsoku"] = {"price": hit["price"], **({"full": True} if hit["full"] else {})}
            hpsa = pick_shinsoku(sh, c["name"], psa10=True)   # PSA10の買取価格（鑑定に出す価値の判断に使う）
            if hpsa: P.setdefault("psa10", {}).setdefault("buy", {})["shinsoku"] = hpsa["price"]
            if c["rarity"] in HIGH_RARITY and KANABELL_BUY_URL:
                kb = kanabell_buy(c["name"], a.dump)
                if kb: buy["kanabell"] = {"price": kb}
            for o in ocr.get(c["key"], []):
                if not o.get("name") or o["name"][:2] in c["name"]:   # 番号一致＋名前の先頭が合えば同一カードとみなす
                    buy["ocr:" + str(o["shop"])] = {"price": o["price"], "src": o.get("src"), "when": o.get("when")}
            if buy: P["buy"] = buy
            if c["rarity"] in HIGH_RARITY or (c["lowest"] or 0) >= LISTING_MIN_PRICE:
                it = dmm_item(c["dmmId"], a.dump); ls = it["listings"]
                if ls:
                    low = min(ls, key=lambda l: l["price"]); P["dmm"] = {"lowest": low["price"], "cond": low["cond"], "listings": ls}
                if it["sold"]: P["dmm"]["sold"] = it["sold"]   # 実際に売れた価格（中央値・件数・枚数）
            if c["rarity"] in SEARCH_RARITY:
                for sk, sc in SHOPS_SEARCH.items():
                    if not sc["base"]: continue
                    try:
                        r = shop_search_price(sc["base"], c["key"], f"{sk}_{c['key'].replace('/', '-')}.html" if a.dump else None)
                        if r: P[sk] = r
                    except Exception as e:
                        log(f"  {sk} {c['key']}: {e}")
            if set_id == "M6a" and c["key"] in M6A_SHOPS:
                s = M6A_SHOPS[c["key"]]
                try:
                    if s.get("cardrush"): P["cardrush"] = cardrush_page(s["cardrush"], a.dump)
                    if s.get("hareruya2"): P["hareruya2"] = shopify_json(HARERUYA.format(id=s["hareruya2"]), f"hareruya2_{c['key'].replace('/', '-')}.json", a.dump)
                    if s.get("torecacamp"): P["torecacamp"] = shopify_json(CAMP.format(id=s["torecacamp"]), f"camp_{c['key'].replace('/', '-')}.json", a.dump)
                except Exception as e:
                    log(f"  {c['key']} shops: {e}")
            for sk in list(P.keys()):   # 検索型の店が PSA10 も返したらまとめ側に反映
                if sk in SHOPS_SEARCH and P[sk].get("psa10"):
                    P.setdefault("psa10", {}); P["psa10"].setdefault("shops", {})[sk] = P[sk]["psa10"]
                    if not P["psa10"].get("lowest") or P[sk]["psa10"] < P["psa10"]["lowest"]: P["psa10"]["lowest"] = P[sk]["psa10"]
            prices[c["key"]] = {"prices": P}
        log(f"  PSA10 付き: {sum(1 for v in prices.values() if v['prices'].get('psa10'))}枚")
        try:
            bid = box_id_for(set_id, entry["name"])
            if bid == 0:   # 0 = 取得しない（DMMにまだBOXが無い弾。似た名前の別商品を拾わせない）
                entry.pop("box", None)   # 前回の実行で誤って入った値が残らないように消す
                log("  BOX 実勢: 取得しない指定（BOX_IDS = 0）"); raise StopIteration
            b = dmm_box_item(bid, a.dump) if bid else None          # ① BOX_IDS で手動指定があればそれ
            if b: log(f"  BOX 商品ID指定: {bid}")
            if not b: b = pick_box(box_index, set_id, entry["name"])   # ② keyword=BOX の一覧からコード照合
            if not b:      # ③ コードも名前も当たらなければ、そのシリーズ名でもう一度だけ引く
                extra = dmm_box_index(a.dump, keyword=box_query(entry["name"])) if box_query(entry["name"]) else []
                ids = {x["dmmId"] for x in box_index}; box_index += [x for x in extra if x["dmmId"] not in ids]
                b = pick_box(extra, set_id, entry["name"])
            if b:
                entry["box"] = {"price": b["lowest"], "when": snap["fetched_at"], "src": "DMMマイカ",
                                "name": b["name"], "dmmId": b["dmmId"], "url": b["url"], "sealed": b["sealed"]}
                if b.get("sold"): entry["box"]["sold"] = b["sold"]
                log(f"  BOX 実勢: ¥{b['lowest']:,}（{b['name']}{'' if b['sealed'] else '・未開封表記なし'}）"
                    + (f" / 成約 中央値¥{b['sold']['med']:,}・{b['sold']['n']}件・{b['sold']['qty']}個" if b.get("sold") else ""))
            else:
                entry.pop("box", None); log("  BOX 実勢: 見つからず")
        except StopIteration:
            pass
        except Exception as e:
            log(f"  BOX: {e}")
        snap["sets"][set_id] = prices
        log(f"{set_id} {entry['name']}: {len(cards)}枚")

    SETS_FILE.write_text(json.dumps(sets_db, ensure_ascii=False, indent=1), encoding="utf-8")
    hist = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    hist.append(snap); OUT.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"saved {OUT} ({len(hist)} snapshots), {SETS_FILE} ({len(sets_db)} sets)")
    close_browser()


if __name__ == "__main__":
    main()
