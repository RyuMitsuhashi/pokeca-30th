#!/usr/bin/env python3
"""
SEO / AIO 用の静的ページ生成。collect.py の出力（sets.json / prices.json）から
  sets/<シリーズID>/index.html            シリーズページ（要約・当たり・BOX期待値・FAQ・ItemList/FAQPage）
  cards/<シリーズID>/<番号>/index.html     カードページ（要約・価格表・店舗別・買取・PSA10・Product/AggregateOffer）
  og/<シリーズID>/<番号>.png                共有用画像（Xで貼ったときのカード）
  sitemap.xml / robots.txt / llms.txt
を作る。各ページには操作用の本体アプリ（index.html）への深いリンクを置く。

環境変数 SITE_URL（例 https://www.soubadex.com）。無ければ GITHUB_REPOSITORY から GitHub Pages のURLを組み立てる。
"""
from __future__ import annotations
import datetime as dt, html, json, os, pathlib, re, sys

ROOT = pathlib.Path(".")
SETS = json.loads((ROOT / "sets.json").read_text(encoding="utf-8")) if (ROOT / "sets.json").exists() else {}
SNAPS = json.loads((ROOT / "prices.json").read_text(encoding="utf-8")) if (ROOT / "prices.json").exists() else []
SITE_NAME = "SOUBADEX"; TAG = "ポケカ相場"
repo = os.environ.get("GITHUB_REPOSITORY", "")
SITE_URL = os.environ.get("SITE_URL") or (f"https://{repo.split('/')[0].lower()}.github.io/{repo.split('/')[1]}" if "/" in repo else "https://example.com")
SITE_URL = SITE_URL.rstrip("/")
JST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(JST)
SET_META = {"M6a": {"box": 24900, "msrp": 7200, "release": "2026-09-16", "ev": 19078}}  # BOX価格・定価・期待値（index.html と同じ値を手で合わせる）
CHASE = {"RGB", "FUR", "SAR", "SR", "UR", "ACE", "HR", "CSR", "CHR", "SSR", "MUR", "CLS"}
BUY_LABEL = {"yuyu": "遊々亭", "shinsoku": "シンソク", "kanabell": "カーナベル", "cardrush": "カードラッシュ"}
SHOP_LABEL = {"cardrush": "カードラッシュ", "hareruya2": "晴れる屋2", "torecacamp": "トレカキャンプ", "shinsoku": "シンソク", "torecalounge": "トレカラウンジ"}

def esc(s): return html.escape(str(s), quote=True)
def yen(v): return "¥" + f"{int(round(v)):,}" if v is not None else "—"
def pct(a, b): return (b - a) / a * 100 if a else None
def fmt_pct(p): return "—" if p is None else ("▲" if p > 0.05 else "▼" if p < -0.05 else "±") + f"{abs(p):.1f}%"
def parse_t(s):
    try: return dt.datetime.fromisoformat(s)
    except Exception: return None
def slug(key): return key.replace("/", "-")


# ---------- スナップショットからカードごとの時系列を組み立てる ----------
def timeline(set_id: str, key: str) -> list[dict]:
    out = []
    for snap in SNAPS:
        t = parse_t(snap.get("fetched_at", "")); rec = None
        if snap.get("v") == 2: rec = ((snap.get("sets") or {}).get(set_id) or {}).get(key)
        elif set_id == "M6a":
            for h in snap.get("cards", []):
                k = h.get("key") or (re.search(r"(\d{3}/103|[RGB]/RGB)", str(h.get("name", ""))) or [None, None])[1]
                if k == key: rec = {"prices": h.get("prices") or ({"dmm": {"lowest": h.get("lowest"), "cond": h.get("cond"), "listings": h.get("listings")}} if h.get("lowest") else {})}
        if not t or not rec: continue
        P = rec.get("prices") or {}
        out.append({"t": t, "P": P})
    return out


def facts(set_id: str, key: str, card: dict) -> dict:
    tl = timeline(set_id, key)
    dmm = [(x["t"], x["P"]["dmm"]["lowest"]) for x in tl if x["P"].get("dmm", {}).get("lowest")]
    psa = [(x["t"], x["P"]["psa10"]["lowest"]) for x in tl if x["P"].get("psa10", {}).get("lowest")]
    last = tl[-1] if tl else None; P = last["P"] if last else {}
    raw = dmm[-1][1] if dmm else (P.get("cardrush", {}).get("sell") if P.get("cardrush") and not P["cardrush"].get("soldout") else None)
    prev = dmm[-2][1] if len(dmm) >= 2 else None
    day = None
    if dmm:
        cutoff = dmm[-1][0] - dt.timedelta(hours=24)
        older = [v for (t, v) in dmm if t <= cutoff]
        day = older[-1] if older else None
    buys = []
    if P.get("cardrush", {}).get("buy"): buys.append(("カードラッシュ", P["cardrush"]["buy"]))
    for k, v in (P.get("buy") or {}).items():
        if v and v.get("price"): buys.append((BUY_LABEL.get(k, k[4:] + "（画像OCR）" if k.startswith("ocr:") else k), v["price"]))
    buys.sort(key=lambda x: -x[1])
    shops = []
    for k, lab in SHOP_LABEL.items():
        v = P.get(k)
        if v and v.get("sell"): shops.append((lab, v["sell"], "売切" if v.get("soldout") else "—"))
    for l in (P.get("dmm") or {}).get("listings") or []: shops.append((l.get("shop"), l.get("price"), l.get("cond") or "—"))
    shops = [s for s in shops if s[1]]; shops.sort(key=lambda x: x[1])
    psa_last = psa[-1][1] if psa else None
    return {"raw": raw, "prev_chg": pct(prev, raw) if prev and raw else None, "day_chg": pct(day, raw) if day and raw else None,
            "psa": psa_last, "ratio": (psa_last / raw) if psa_last and raw else None, "buys": buys, "shops": shops,
            "spread": ((raw - buys[0][1]) / raw * 100) if raw and buys and buys[0][1] <= raw else None,
            "history": dmm[-40:], "psa_history": psa[-40:], "listings": len((P.get("dmm") or {}).get("listings") or []),
            "updated": last["t"] if last else None, "dmmId": card.get("dmmId")}


# ---------- 共通の枠 ----------
CSS = """body{margin:0;background:#0F1012;color:#ECEAE4;font-family:"BIZ UDPGothic","Hiragino Sans",system-ui,sans-serif;line-height:1.6}
a{color:#2FD4A5}.wrap{max-width:960px;margin:0 auto;padding:18px}.top{display:flex;gap:12px;align-items:center;border-bottom:1px solid #2A2E34;padding:10px 18px}
.top a{color:#ECEAE4;text-decoration:none}.top b{font-family:"IBM Plex Mono",monospace;letter-spacing:.08em}.top small{color:#9BA0A8}
h1{font-size:1.4rem;margin:12px 0 4px}h2{font-size:1.05rem;margin:22px 0 8px;border-bottom:1px solid #2A2E34;padding-bottom:4px}
table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{padding:6px 8px;border-bottom:1px solid #212429;text-align:left}th{color:#9BA0A8;font-weight:400;font-size:.8rem}td.r,th.r{text-align:right;font-family:"IBM Plex Mono",monospace}
.up{color:#2ECC71}.down{color:#E5484D}.muted{color:#9BA0A8}.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:1px;background:#2A2E34;border:1px solid #2A2E34;margin:10px 0}
.kv div{background:#151719;padding:10px}.kv .l{color:#9BA0A8;font-size:.74rem}.kv .v{font-family:"IBM Plex Mono",monospace;font-size:1.15rem}
.btn{display:inline-block;background:#2FD4A5;color:#0F1012;font-weight:700;text-decoration:none;padding:8px 14px;margin:10px 0}.foot{color:#6B7078;font-size:.78rem;margin-top:28px;border-top:1px solid #2A2E34;padding-top:10px}
.crumb{font-size:.8rem;color:#9BA0A8}.crumb a{color:#9BA0A8}
.ad{position:relative;border:1px dashed #2A2E34;padding:10px;margin:14px 0;min-height:100px}.adl{position:absolute;left:8px;top:-8px;font-size:.62rem;color:#6B7078;background:#0F1012;padding:0 6px}"""


ADS_CLIENT = os.environ.get("ADSENSE_CLIENT", "").strip(); ADS_SLOT = os.environ.get("ADSENSE_SLOT", "").strip()
def ad_block():
    if not ADS_CLIENT or not ADS_SLOT: return ""
    return (f'<div class="ad"><span class="adl">広告</span><ins class="adsbygoogle" style="display:block" data-ad-client="{esc(ADS_CLIENT)}" data-ad-slot="{esc(ADS_SLOT)}" data-ad-format="auto" data-full-width-responsive="true"></ins>'
            '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>')
def ad_head():
    return f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={esc(ADS_CLIENT)}" crossorigin="anonymous"></script>' if ADS_CLIENT and ADS_SLOT else ""

def page(title, desc, canon, body, og_img=None, jsonld=None, breadcrumbs=None):
    ld = [j for j in ([jsonld] if jsonld else [])]
    if breadcrumbs:
        ld.append({"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(breadcrumbs)]})
    lds = "".join(f'<script type="application/ld+json">{json.dumps(j, ensure_ascii=False)}</script>' for j in ld)
    og = f'<meta property="og:image" content="{esc(og_img)}"><meta name="twitter:card" content="summary_large_image">' if og_img else '<meta name="twitter:card" content="summary">'
    crumb = " › ".join(f'<a href="{esc(u)}">{esc(n)}</a>' for n, u in (breadcrumbs or [])[:-1]) + (f" › {esc(breadcrumbs[-1][0])}" if breadcrumbs else "")
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}"><link rel="canonical" href="{esc(canon)}">
<meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canon)}"><meta property="og:site_name" content="{SITE_NAME}"><meta property="og:type" content="website">{og}
<link href="https://fonts.googleapis.com/css2?family=BIZ+UDPGothic:wght@400;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet"><style>{CSS}</style>{lds}{ad_head()}</head>
<body><div class="top"><a href="{SITE_URL}/"><b>{SITE_NAME}</b> <small>{TAG}</small></a></div><div class="wrap"><div class="crumb">{crumb}</div>{body}
<div class="foot">価格は各サイト掲載時点の値で、実際の店頭・取引価格とは異なる場合があります。出典：DMMマイカ／カードラッシュ／遊々亭／シンソク ほか。©Pokémon／Nintendo／Creatures／GAME FREAK　<a href="{SITE_URL}/#/about">このサイトについて</a></div></div></body></html>"""


# ---------- OG画像 ----------
def og_image(path: pathlib.Path, title: str, sub: str, price: str, chg: str):
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    fonts = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"]
    fp = next((f for f in fonts if pathlib.Path(f).exists()), None)
    im = Image.new("RGB", (1200, 630), (15, 16, 18)); d = ImageDraw.Draw(im)
    def F(sz):
        try: return ImageFont.truetype(fp, sz) if fp else ImageFont.load_default()
        except Exception: return ImageFont.load_default()
    d.rectangle([0, 0, 1200, 8], fill=(47, 212, 165))
    d.text((60, 60), SITE_NAME, font=F(34), fill=(47, 212, 165))
    d.text((60, 130), title[:28], font=F(64), fill=(236, 234, 228))
    d.text((60, 215), sub[:60], font=F(30), fill=(155, 160, 168))
    d.text((60, 330), price, font=F(110), fill=(236, 234, 228))
    d.text((60, 470), chg, font=F(48), fill=(46, 204, 113) if chg.startswith("▲") else (229, 72, 77) if chg.startswith("▼") else (155, 160, 168))
    d.text((60, 560), f"{NOW.strftime('%Y/%m/%d %H:%M')} 時点 ・ 最安値（DMMマイカ ほか）", font=F(26), fill=(107, 112, 120))
    path.parent.mkdir(parents=True, exist_ok=True); im.save(path, optimize=True); return True


# ---------- ページ生成 ----------
def build():
    urls = []
    for set_id, st in SETS.items():
        cards = st.get("cards") or {}
        name = st.get("name") or set_id
        rows = []
        for key, c in cards.items():
            f = facts(set_id, key, c)
            rows.append((key, c, f))
        priced = [r for r in rows if r[2]["raw"]]
        priced.sort(key=lambda r: -r[2]["raw"])
        set_url = f"{SITE_URL}/sets/{set_id}/"
        # ---- カードページ ----
        keys = [r[0] for r in rows]
        for i, (key, c, f) in enumerate(rows):
            url = f"{SITE_URL}/cards/{set_id}/{slug(key)}/"
            cname = c.get("name") or key; rar = c.get("rarity") or ""
            title = f"{cname}{' ' + rar if rar else ''} {key} の相場・最安値・買取価格｜{SITE_NAME}"
            when = f["updated"].strftime("%Y年%m月%d日 %H:%M") if f["updated"] else NOW.strftime("%Y年%m月%d日")
            desc = (f"{when}時点、{cname}（{name} {key}{'・' + rar if rar else ''}）の最安値は{yen(f['raw'])}。"
                    + (f"前回比{fmt_pct(f['prev_chg'])}。" if f["prev_chg"] is not None else "")
                    + (f"買取最高は{yen(f['buys'][0][1])}（{f['buys'][0][0]}）。" if f["buys"] else "")
                    + (f"PSA10は{yen(f['psa'])}（素体の{f['ratio']:.1f}倍）。" if f["psa"] and f["ratio"] else ""))
            app = f"{SITE_URL}/#/card/{set_id}/{key.replace('/', '%2F')}"
            hist = "".join(f"<tr><td>{t.strftime('%m/%d %H:%M')}</td><td class='r'>{yen(v)}</td></tr>" for t, v in reversed(f["history"]))
            shops = "".join(f"<tr><td>{esc(s)}</td><td class='r'>{yen(p)}</td><td>{esc(cd)}</td></tr>" for s, p, cd in f["shops"][:12])
            buys = "".join(f"<tr><td>{esc(s)}</td><td class='r'>{yen(p)}</td></tr>" for s, p in f["buys"])
            prev_l = f'<a href="{SITE_URL}/cards/{set_id}/{slug(keys[i-1])}/">← {esc(cards[keys[i-1]].get("name",""))}</a>' if i > 0 else ""
            next_l = f'<a href="{SITE_URL}/cards/{set_id}/{slug(keys[i+1])}/">{esc(cards[keys[i+1]].get("name",""))} →</a>' if i + 1 < len(keys) else ""
            dmm_link = f"https://myca.dmm.com/pokemon-trading-card-game/items/single-card/{c['dmmId']}" if c.get("dmmId") else "https://myca.dmm.com/"
            body = f"""<h1>{esc(cname)} <span class="muted">{esc(rar)} {esc(key)}</span></h1><p class="muted">{esc(name)}・{when}時点</p>
<p>{esc(desc)}</p>
<div class="kv"><div><div class="l">素体 最安値</div><div class="v">{yen(f['raw'])}</div></div><div><div class="l">前回比</div><div class="v {'up' if (f['prev_chg'] or 0)>0.05 else 'down' if (f['prev_chg'] or 0)<-0.05 else ''}">{fmt_pct(f['prev_chg'])}</div></div>
<div><div class="l">PSA10 最安</div><div class="v">{yen(f['psa'])}</div></div><div><div class="l">PSA倍率</div><div class="v">{f"{f['ratio']:.2f}×" if f['ratio'] else '—'}</div></div>
<div><div class="l">買取最高</div><div class="v">{yen(f['buys'][0][1]) if f['buys'] else '—'}</div></div><div><div class="l">スプレッド</div><div class="v">{f"{f['spread']:.0f}%" if f['spread'] is not None else '—'}</div></div></div>
<a class="btn" href="{app}">チャートと店舗別価格をアプリで見る</a>
{ad_block()}
<h2>価格の推移（素体・最安値）</h2><table><tr><th>日時</th><th class="r">最安値</th></tr>{hist or '<tr><td colspan=2 class=muted>まだ履歴がありません</td></tr>'}</table>
<h2>店舗別の販売価格</h2><table><tr><th>店舗</th><th class="r">価格</th><th>状態</th></tr>{shops or '<tr><td colspan=3 class=muted>データなし</td></tr>'}</table>
{ad_block()}
<h2>買取価格（売るならどこ）</h2><table><tr><th>店舗</th><th class="r">買取価格</th></tr>{buys or '<tr><td colspan=2 class=muted>データなし</td></tr>'}</table>
<h2>このカードを探す</h2><p><a href="{dmm_link}" rel="noopener">DMMマイカ</a> ／ <a href="https://www.pokemon-card.com/card-search/index.php?keyword={esc(cname)}" rel="noopener">公式カード検索</a> ／ <a href="https://snkrdunk.com/search?keyword={esc(cname + ' ' + key)}" rel="noopener">スニダンで見る</a></p>
<p class="muted">{prev_l} {' ｜ ' if prev_l and next_l else ''} {next_l}</p>"""
            jsonld = {"@context": "https://schema.org", "@type": "Product", "name": f"{cname} {rar} {key}".strip(), "category": "ポケモンカードゲーム", "brand": {"@type": "Brand", "name": "ポケモンカードゲーム"},
                      "url": url, "description": desc}
            if f["shops"]:
                jsonld["offers"] = {"@type": "AggregateOffer", "priceCurrency": "JPY", "lowPrice": min(s[1] for s in f["shops"]), "highPrice": max(s[1] for s in f["shops"]), "offerCount": len(f["shops"])}
            elif f["raw"]:
                jsonld["offers"] = {"@type": "AggregateOffer", "priceCurrency": "JPY", "lowPrice": f["raw"], "highPrice": f["raw"], "offerCount": 1}
            og = None
            if f["raw"]:
                ogp = ROOT / "og" / set_id / f"{slug(key)}.png"
                if og_image(ogp, cname, f"{name} {key} {rar}", yen(f["raw"]), fmt_pct(f["prev_chg"]) + (" 前回比" if f["prev_chg"] is not None else "")): og = f"{SITE_URL}/og/{set_id}/{slug(key)}.png"
            out = ROOT / "cards" / set_id / slug(key) / "index.html"; out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(page(title, desc, url, body, og, jsonld, [("ホーム", f"{SITE_URL}/"), (name, set_url), (cname, url)]), encoding="utf-8")
            urls.append((url, f["updated"] or NOW))
        # ---- シリーズページ ----
        meta = dict(SET_META.get(set_id, {})); m = meta
        sbox = (SETS.get(set_id) or {}).get("box") or {}   # collect.py が一覧のBOX行から取った実勢価格を優先
        if sbox.get("price"): m["box"] = sbox["price"]
        top = priced[:20]
        chase = [r for r in rows if (r[1].get("rarity") or "") in CHASE and r[2]["raw"] and r[2]["day_chg"] is not None]
        idx = sum(r[2]["day_chg"] for r in chase) / len(chase) if chase else None
        ups = sorted([r for r in rows if r[2]["day_chg"] is not None and r[2]["day_chg"] > 0.05], key=lambda r: -r[2]["day_chg"])[:5]
        downs = sorted([r for r in rows if r[2]["day_chg"] is not None and r[2]["day_chg"] < -0.05], key=lambda r: r[2]["day_chg"])[:5]
        title = f"{name} の相場・当たりカード・BOX期待値｜{SITE_NAME}"
        desc = (f"{NOW.strftime('%Y年%m月%d日')}時点の{name}（{set_id}）の相場。価格データのあるカード{len(priced)}枚。"
                + (f"最高額は{top[0][1].get('name')}の{yen(top[0][2]['raw'])}。" if top else "")
                + (f"主要カードの指数は24hで{fmt_pct(idx)}。" if idx is not None else "")
                + (f"BOXは実勢{yen(m['box'])}" + (f"（定価{yen(m['msrp'])}）" if m.get("msrp") else "")
                   + (f"、期待値{yen(m['ev'])}" if m.get("ev") else "") + "。" if m.get("box") else ""))
        trow = "".join(f"<tr><td><a href='{SITE_URL}/cards/{set_id}/{slug(k)}/'>{esc(c.get('name',''))}</a> <span class=muted>{esc(c.get('rarity',''))} {esc(k)}</span></td><td class='r'>{yen(f['raw'])}</td><td class='r {'up' if (f['day_chg'] or 0)>0.05 else 'down' if (f['day_chg'] or 0)<-0.05 else ''}'>{fmt_pct(f['day_chg'])}</td><td class='r'>{yen(f['psa'])}</td><td class='r'>{yen(f['buys'][0][1]) if f['buys'] else '—'}</td></tr>" for k, c, f in top)
        mv = lambda L: "".join(f"<li><a href='{SITE_URL}/cards/{set_id}/{slug(k)}/'>{esc(c.get('name',''))}</a> {yen(f['raw'])} <span class='{'up' if f['day_chg']>0 else 'down'}'>{fmt_pct(f['day_chg'])}</span></li>" for k, c, f in L) or "<li class=muted>該当なし</li>"
        faq = [(f"{name}の当たりカードは？", f"価格の高い順に、{ '、'.join(c.get('name','') + '（' + yen(f['raw']) + '）' for k, c, f in top[:5]) }です（{NOW.strftime('%Y/%m/%d')}時点の最安値）。" if top else "集計中です。"),
               (f"{name}のBOXは開ける価値がある？",
                (f"実勢価格{yen(m['box'])}に対して期待値は{yen(m['ev'])}で、差は{yen(m['ev']-m['box'])}。"
                 + (f"定価{yen(m['msrp'])}で買えるなら開ける価値があります。" if m.get("msrp") else "") if m.get("box") and m.get("ev")
                 else f"BOXの実勢価格は{yen(m['box'])}です。封入率と期待値は集計中です。" if m.get("box") else "封入率と期待値は集計中です。")),
               (f"{name}の相場は上がっている？", (f"主要カードの指数は24hで{fmt_pct(idx)}です。" if idx is not None else "推移は取得を重ねると表示されます。") + "詳しい推移は各カードのページで確認できます。")]
        body = f"""<h1>{esc(name)} <span class="muted">{esc(set_id)}</span></h1><p class="muted">{NOW.strftime('%Y年%m月%d日 %H:%M')}時点</p><p>{esc(desc)}</p>
<div class="kv"><div><div class="l">価格データのあるカード</div><div class="v">{len(priced)} / {len(rows)}</div></div><div><div class="l">主要カード指数（24h）</div><div class="v">{fmt_pct(idx)}</div></div>
<div><div class="l">BOX 実勢／定価</div><div class="v">{yen(m['box']) if m.get('box') else '—'} / {yen(m['msrp']) if m.get('msrp') else '—'}</div></div><div><div class="l">期待値（復刻まで）</div><div class="v">{yen(m['ev']) if m.get('ev') else '—'}</div></div></div>
<a class="btn" href="{SITE_URL}/#/set/{set_id}">ランキング・一覧をアプリで見る</a>
{ad_block()}
<h2>高額カード トップ20</h2><table><tr><th>カード</th><th class="r">素体最安</th><th class="r">24h</th><th class="r">PSA10</th><th class="r">買取最高</th></tr>{trow}</table>
<h2>24hの値動き</h2><p><b>上昇</b></p><ul>{mv(ups)}</ul><p><b>下落</b></p><ul>{mv(downs)}</ul>
<h2>よくある質問</h2>{''.join(f'<p><b>Q. {esc(q)}</b><br>A. {esc(a)}</p>' for q, a in faq)}
<h2>収録カード一覧</h2><p>{' ／ '.join(f"<a href='{SITE_URL}/cards/{set_id}/{slug(k)}/'>{esc(c.get('name',''))} {esc(k)}</a>" for k, c, f in rows)}</p>"""
        jsonld = {"@context": "https://schema.org", "@type": "ItemList", "name": f"{name} 高額カード", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": c.get("name", ""), "url": f"{SITE_URL}/cards/{set_id}/{slug(k)}/"} for i, (k, c, f) in enumerate(top)]}
        faqld = {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}
        outp = ROOT / "sets" / set_id / "index.html"; outp.parent.mkdir(parents=True, exist_ok=True)
        og = None
        if top and og_image(ROOT / "og" / set_id / "set.png", name, f"{set_id} ・ 価格データ {len(priced)}枚", f"指数 {fmt_pct(idx)}" if idx is not None else "相場", f"最高額 {top[0][1].get('name','')} {yen(top[0][2]['raw'])}"): og = f"{SITE_URL}/og/{set_id}/set.png"
        html_ = page(title, desc, set_url, body, og, jsonld, [("ホーム", f"{SITE_URL}/"), (name, set_url)])
        html_ = html_.replace("</head>", f'<script type="application/ld+json">{json.dumps(faqld, ensure_ascii=False)}</script></head>')
        outp.write_text(html_, encoding="utf-8"); urls.append((set_url, NOW))
        print(f"{set_id}: cards {len(rows)}, priced {len(priced)}", file=sys.stderr)

    # ---- sitemap / robots / llms.txt ----
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">', f"<url><loc>{SITE_URL}/</loc><lastmod>{NOW.date()}</lastmod><changefreq>hourly</changefreq></url>"]
    for u, t in urls: sm.append(f"<url><loc>{esc(u)}</loc><lastmod>{t.date()}</lastmod><changefreq>daily</changefreq></url>")
    sm.append("</urlset>"); (ROOT / "sitemap.xml").write_text("\n".join(sm), encoding="utf-8")
    robots = ("# HTMLは引用歓迎、生データ（JSON）と共有画像の一括取得は不可\n"
              "User-agent: *\nAllow: /\nDisallow: /prices.json\nDisallow: /sets.json\nDisallow: /buy_ocr.json\nDisallow: /ids.json\nDisallow: /tcgdex-\nDisallow: /data/\nDisallow: /og/\n\n"
              "User-agent: GPTBot\nAllow: /\nDisallow: /prices.json\nDisallow: /sets.json\nDisallow: /data/\n"
              "User-agent: ClaudeBot\nAllow: /\nDisallow: /prices.json\nDisallow: /sets.json\nDisallow: /data/\n"
              "User-agent: PerplexityBot\nAllow: /\nDisallow: /prices.json\nDisallow: /sets.json\nDisallow: /data/\n"
              "User-agent: Google-Extended\nAllow: /\n\n"
              f"Sitemap: {SITE_URL}/sitemap.xml\n")
    (ROOT / "robots.txt").write_text(robots, encoding="utf-8")
    (ROOT / "llms.txt").write_text(f"# {SITE_NAME} ｜ {TAG}\n\n> ポケモンカードの販売価格・買取価格・PSA10価格を、DMMマイカ・カードラッシュ・遊々亭・シンソクなどの公開ページから1日2回集計している相場サイト。シリーズ別のBOX期待値、主要カードの指数、鑑定価値（PSA10÷素体）を掲載。\n\n## ページ\n" + "\n".join(f"- [{u}]({u})" for u, t in urls[:500]) + "\n", encoding="utf-8")
    print(f"pages: {len(urls)}, sitemap written", file=sys.stderr)


if __name__ == "__main__":
    build()
