#!/usr/bin/env python3
"""
画像の買取表を Claude API で読み取り、buy_ocr.json に書く（第1段：ショップ公式サイトに貼られた画像が対象）。

設定：ocr_sources.json（例）
[
  {"shop": "トレカラウンジ", "page": "https://example.com/kaitori", "match": "kaitori"},   # ページ内の <img src> に match を含む画像を全部読む
  {"shop": "シンソク", "image": "https://example.com/list.png"}                              # 画像URLを直接
]
環境変数 ANTHROPIC_API_KEY が必要（GitHub Actions では Secrets に入れる）。無ければ何もしない。
"""
from __future__ import annotations
import base64, json, os, pathlib, re, sys, datetime as dt
import requests

KEY = os.environ.get("ANTHROPIC_API_KEY")
SRC = pathlib.Path("ocr_sources.json"); OUT = pathlib.Path("buy_ocr.json")
PROMPT = ("これはトレーディングカードショップの買取価格表の画像です。表に載っているカードを全部、JSON配列だけで返してください。"
          "各要素は {\"name\": カード名, \"no\": \"135/103\" 形式のカード番号(無ければnull), \"rarity\": レアリティ(無ければnull), "
          "\"price\": 買取価格の整数(円), \"note\": 条件(美品限定・枚数制限など、無ければnull)} です。説明文は不要です。")


def ocr_image(url: str) -> list[dict]:
    img = requests.get(url, timeout=60); img.raise_for_status()
    mime = img.headers.get("Content-Type", "image/jpeg").split(";")[0]
    if mime not in ("image/jpeg", "image/png", "image/webp", "image/gif"): mime = "image/jpeg"
    body = {"model": "claude-sonnet-4-6", "max_tokens": 4000, "messages": [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(img.content).decode()}},
        {"type": "text", "text": PROMPT}]}]}
    r = requests.post("https://api.anthropic.com/v1/messages", json=body, timeout=180,
                      headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    r.raise_for_status()
    text = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\[.*\]", text, re.S)
    rows = json.loads(m.group(0)) if m else []
    return [x for x in rows if isinstance(x, dict) and x.get("price")]


def main():
    if not KEY: print("ANTHROPIC_API_KEY なし。OCR をスキップ", file=sys.stderr); return
    if not SRC.exists(): print("ocr_sources.json なし。OCR をスキップ", file=sys.stderr); return
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M")
    results = []
    for src in json.loads(SRC.read_text(encoding="utf-8")):
        images = [src["image"]] if src.get("image") else []
        if src.get("page"):
            try:
                html = requests.get(src["page"], timeout=60, headers={"User-Agent": "Mozilla/5.0 (compatible; SOUBADEX-bot/2.0; +https://soubadex.com/#/about)"}).text
                for u in re.findall(r'<img[^>]+src="([^"]+)"', html):
                    if src.get("match", "") in u: images.append(requests.compat.urljoin(src["page"], u))
            except requests.RequestException as e:
                print(f"{src.get('shop')}: {e}", file=sys.stderr)
        for u in dict.fromkeys(images):
            try:
                rows = ocr_image(u)
                results.append({"shop": src.get("shop"), "src": src.get("page") or u, "image": u, "date": today, "rows": rows})
                print(f"{src.get('shop')}: {u} → {len(rows)}行", file=sys.stderr)
            except Exception as e:
                print(f"{src.get('shop')}: {u} 失敗 {e}", file=sys.stderr)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
