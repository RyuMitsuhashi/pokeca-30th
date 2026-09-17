# 1日2回（JST 9:00 / 21:00）各サイトの公開ページから価格を取り、prices.json をコミットする。
# 同じリポジトリを GitHub Pages で公開しておけば、ダッシュボードが同一オリジンの prices.json を読める。
name: fetch-prices

on:
  schedule:
    - cron: "0 0,12 * * *"   # UTC 0:00 / 12:00 = JST 9:00 / 21:00
  workflow_dispatch:

permissions:
  contents: write

jobs:
  fetch:
    runs-on: ubuntu-latest
    timeout-minutes: 120
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install requests beautifulsoup4 playwright
      - run: python -m playwright install --with-deps chromium
      - name: OCR image buylists (needs ANTHROPIC_API_KEY secret)
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python ocr_buylist.py
      - run: python collect.py
      - name: commit results
        run: |
          git config user.name  "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          for f in prices.json ids.json sets.json buy_ocr.json tcgdex-*.json; do [ -f "$f" ] && git add "$f"; done
          git commit -m "prices: $(date -u +%Y-%m-%dT%H:%M)Z" || echo "no changes"
          git push
