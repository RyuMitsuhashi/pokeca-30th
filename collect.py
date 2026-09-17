#!/usr/bin/env python3
"""
30th CELEBRATION 相場図鑑 のデータ収集。各ECサイトの公開ページから直接価格を取り、prices.json にスナップショットを追記する。

取得元（いずれも公開ページ。1日1〜2回、リクエスト間隔 WAIT 秒で控えめに）
  dmm        DMMマイカ 通販サイト …… 全出品（店舗・価格・状態）と最安値。商品ページのHTMLをそのまま解析（確認済み）
  cardrush   カードラッシュ …… 販売価格・買取価格。商品ページのHTMLを解析（初回実行時に --dump で確認してください）
  hareruya2  晴れる屋2 …… Shopify なので /products/<id>.json（公式のJSON）から価格を取る
  torecacamp トレカキャンプ …… 同じく Shopify の JSON
メルカリ・ヤフオクは規約上の自動取得禁止・API非公開のため対象外。スニダンは規約確認後に追加予定。

出力（prices.json、配列の末尾に追記）
  {"fetched_at": "...", "cards": [ {"key": "135/103", "name": "ミュウex",
      "prices": {"dmm": {"lowest": 18800, "cond": "A", "listings": [{"shop","price","cond"}...]},
                 "cardrush": {"sell": 18800, "buy": 10000}, "hareruya2": {"sell": 28000}, "torecacamp": {"sell": 16800}}} ] }

使い方
  pip install requests beautifulsoup4
  python collect.py                 # 全カード・全ソース
  python collect.py --only dmm      # ソースを絞る（カンマ区切り）
  python collect.py --dump          # 取得したHTML/JSONを ./dump/ に保存（解析が外れたときの調査用）
"""
from __future__ import annotations
import argparse, datetime as dt, json, pathlib, re, sys, time
import requests
from bs4 import BeautifulSoup

WAIT = 2.0
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; pokeca-30th-zukan/0.3; +mailto:you@example.com)", "Accept-Language": "ja,en;q=0.8"}
OUT = pathlib.Path("prices.json"); IDS = pathlib.Path("ids.json"); DUMP = pathlib.Path("dump")
JST = dt.timezone(dt.timedelta(hours=9))
DMM = "https://myca.dmm.com/pokemon-trading-card-game/items/single-card/{id}"
RUSH = "https://www.cardrush-pokemon.jp/product/{id}"
HARERUYA = "https://www.hareruya2.com/products/{id}.json"
CAMP = "https://torecacamp-pokemon.com/products/{id}.json"

# 追跡カード：key → 各サイトの商品ID（2026-09-17時点。空欄は未確認）
CARDS = {
 "R/RGB":   {"name":"ミュウ（赤）",        "cardrush":85241},
 "G/RGB":   {"name":"ミュウ（緑）",        "cardrush":85242},
 "B/RGB":   {"name":"ミュウ（青）",        "dmm":374885, "cardrush":85243, "hareruya2":"10265831440704"},
 "135/103": {"name":"ミュウex FUR",       "dmm":374555, "cardrush":85240, "hareruya2":"10265831145792", "torecacamp":"rc_it1a2gnsix5q_ecj6"},
 "134/103": {"name":"ミュウツーex FUR",    "dmm":374545, "cardrush":85239, "torecacamp":"rc_it1qfx9a9xkk_opse"},
 "126/103": {"name":"ピカチュウex SAR 昼", "cardrush":85231, "hareruya2":"10265832587584", "torecacamp":"rc_ituakuzx3s6w_djab"},
 "127/103": {"name":"ピカチュウex SAR 夜", "dmm":374475, "cardrush":85232, "hareruya2":"10265831899456"},
 "129/103": {"name":"ミュウex SAR",       "cardrush":85234, "hareruya2":"10265831473472"},
 "131/103": {"name":"ゲンガーex SAR",     "cardrush":85236, "hareruya2":"10265831342400"},
 "128/103": {"name":"ミュウツーex SAR",   "cardrush":85233, "hareruya2":"10265831964992"},
 "130/103": {"name":"ニンフィアex SAR",   "dmm":374505, "cardrush":85235, "hareruya2":"10265831768384"},
 "132/103": {"name":"ジラーチex SAR",     "dmm":374525, "cardrush":85237, "hareruya2":"10265831244096"},
 "125/103": {"name":"ゲッコウガex SAR",   "dmm":374455, "cardrush":85230, "hareruya2":"10265832358208"},
 "133/103": {"name":"ボーマンダex SAR",   "cardrush":85238, "hareruya2":"10265831407936"},
 "124/103": {"name":"ホゲータex SAR",     "cardrush":85229, "hareruya2":"10265835176256", "torecacamp":"rc_itexi5fvupgs_esux"},
 "142/103": {"name":"ルギア 復刻版",      "cardrush":85117, "hareruya2":"50719"},
 "137/103": {"name":"リザードン 復刻版",  "dmm":374575, "cardrush":85112, "hareruya2":"10265836388672", "torecacamp":"rc_it9lhproroxw_voqr"},
 "165/103": {"name":"コイキング 復刻版",  "dmm":374855, "cardrush":85139, "hareruya2":"10265837830464", "torecacamp":"rc_itd2qz5fwkb4_0nek"},
 "150/103": {"name":"ゲンガー 復刻版",    "dmm":374705, "cardrush":85125, "hareruya2":"10265837568320"},
 "136/103": {"name":"ピカチュウ 復刻版",  "dmm":374565, "cardrush":85111, "hareruya2":"10265836814656", "torecacamp":"rc_itaoolmbea40_9bnm"},
 "141/103": {"name":"ひかるセレビィ 復刻版","dmm":374615, "cardrush":85116, "hareruya2":"10265838092608"},
 "151/103": {"name":"ダークライ&クレセリア 復刻版（上）","dmm":374713, "cardrush":85126, "hareruya2":"10265837994304"},
 "163/103": {"name":"ミュウVMAX 復刻版",  "dmm":374835, "cardrush":85137},
 "160/103": {"name":"ピカチュウ&ゼクロムGX 復刻版","dmm":374805, "cardrush":85134},
 "154/103": {"name":"レックウザEX 復刻版","dmm":374745, "cardrush":85128},
 "156/103": {"name":"MサーナイトEX 復刻版","dmm":374765, "cardrush":85130},
 "162/103": {"name":"ライコウ 復刻版",    "dmm":374825, "cardrush":85136},
 "153/103": {"name":"N 復刻版",           "dmm":374735, "cardrush":85127},
 "138/103": {"name":"カスミ 復刻版",      "dmm":374585, "cardrush":85113},
 "144/103": {"name":"わるいバンギラス 復刻版","dmm":374645, "cardrush":85119},
}
PRICE = re.compile(r"[¥￥]\s?([\d,]+)|([\d,]+)\s?円")
LISTING = re.compile(r"(?P<shop>[^\n]+)\n(?:SALE中\n)?[¥￥](?P<price>[\d,]+)[^\n]*\n状態(?P<cond>[A-Z][+\-]?)")
KEY = re.compile(r"(\d{3}/103|[RGB]/RGB)")
LINK = re.compile(r'href="(?:https://myca\.dmm\.com)?/pokemon-trading-card-game/items/single-card/(\d+)"[^>]*>(.*?)</a>', re.S)


def get(url: str, dump_name: str | None) -> str:
    r = requests.get(url, headers=HEADERS, timeout=30); r.raise_for_status()
    if dump_name:
        DUMP.mkdir(exist_ok=True); (DUMP / dump_name).write_text(r.text, encoding="utf-8")
    time.sleep(WAIT); return r.text


def yen(s): return int(str(s).replace(",", "")) if s else None


# ---- DMMマイカ ----
def dmm_page(cid, dump):
    html = get(DMM.format(id=cid), f"dmm_{cid}.html" if dump else None)
    soup = BeautifulSoup(html, "html.parser"); text = soup.get_text("\n", strip=True)
    i = text.find("他の出品情報"); sec = text[i:] if i >= 0 else text
    j = sec.find("関連カード"); sec = sec[:j] if j > 0 else sec
    ls = [{"shop": m["shop"].strip(), "price": yen(m["price"]), "cond": m["cond"]} for m in LISTING.finditer(sec)
          if not m["shop"].startswith(("他の出品情報", "状態"))]
    low = min((l for l in ls if l["price"]), key=lambda l: l["price"], default=None)
    return {"lowest": low["price"] if low else None, "cond": low["cond"] if low else None, "listings": ls}, html


def dmm_discover(dump) -> dict:
    """未確認のDMM商品IDを、既知の商品ページの「関連カード」リンクから探して ids.json に貯める"""
    known = json.loads(IDS.read_text(encoding="utf-8")) if IDS.exists() else {}
    for k, c in CARDS.items():
        if "dmm" not in c and k in known: c["dmm"] = int(known[k])
    missing = [k for k, c in CARDS.items() if "dmm" not in c]
    if not missing: return known
    queue = [c["dmm"] for c in CARDS.values() if "dmm" in c]; seen = set()
    while missing and queue and len(seen) < 30:
        cid = queue.pop(0)
        if cid in seen: continue
        seen.add(cid)
        html = get(DMM.format(id=cid), None)
        for m in LINK.finditer(html):
            name = BeautifulSoup(m.group(2), "html.parser").get_text(" ", strip=True); mk = KEY.search(name)
            if name and mk and mk.group(1) not in known:
                known[mk.group(1)] = int(m.group(1)); queue.append(int(m.group(1)))
        for k in list(missing):
            if k in known: CARDS[k]["dmm"] = int(known[k]); missing.remove(k)
    IDS.write_text(json.dumps(known, ensure_ascii=False, indent=1), encoding="utf-8")
    if missing: print(f"dmm id unresolved: {missing}", file=sys.stderr)
    return known


# ---- カードラッシュ ----
def cardrush_page(pid, dump):
    """販売価格と買取価格。ページ構造は初回に dump で確認して、必要なら下の正規表現を直す"""
    html = get(RUSH.format(id=pid), f"cardrush_{pid}.html" if dump else None)
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    def near(label):
        i = text.find(label)
        if i < 0: return None
        m = PRICE.search(text[i:i + 300]); return yen(m.group(1) or m.group(2)) if m else None
    sell = near("販売価格") or near("価格")
    buy = near("買取価格")
    return {"sell": sell, "buy": buy, "verify": sell is None}


# ---- Shopify（晴れる屋2・トレカキャンプ） ----
def shopify_json(url, dump_name, dump):
    txt = get(url, dump_name if dump else None)
    p = json.loads(txt)["product"]
    vs = [v for v in p.get("variants", []) if v.get("available", True)] or p.get("variants", [])
    price = min((float(v["price"]) for v in vs if v.get("price")), default=None)
    if price and price > 1_000_000 and float(vs[0]["price"]) % 100 == 0: price = price / 100  # cents で返る店への保険
    return {"sell": int(price) if price else None, "title": p.get("title")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="dmm,cardrush,hareruya2,torecacamp"); ap.add_argument("--dump", action="store_true")
    a = ap.parse_args(); only = set(a.only.split(","))
    if "dmm" in only: dmm_discover(a.dump)
    cards = []
    for key, c in CARDS.items():
        P = {}
        try:
            if "dmm" in only and c.get("dmm"): P["dmm"], _ = dmm_page(c["dmm"], a.dump)
            if "cardrush" in only and c.get("cardrush"): P["cardrush"] = cardrush_page(c["cardrush"], a.dump)
            if "hareruya2" in only and c.get("hareruya2"): P["hareruya2"] = shopify_json(HARERUYA.format(id=c["hareruya2"]), f"hareruya2_{key.replace('/','-')}.json", a.dump)
            if "torecacamp" in only and c.get("torecacamp"): P["torecacamp"] = shopify_json(CAMP.format(id=c["torecacamp"]), f"camp_{key.replace('/','-')}.json", a.dump)
        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"  {key}: {e}", file=sys.stderr)
        cards.append({"key": key, "name": c["name"], "prices": P})
        print(f"  {key} {c['name']}: " + ", ".join(f"{k}={v.get('lowest', v.get('sell'))}" for k, v in P.items()), file=sys.stderr)
    snap = {"fetched_at": dt.datetime.now(JST).isoformat(timespec="minutes"), "cards": cards}
    hist = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else []
    hist.append(snap); OUT.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {OUT} ({len(hist)} snapshots)", file=sys.stderr)


if __name__ == "__main__":
    main()
