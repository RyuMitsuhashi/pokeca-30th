#!/usr/bin/env python3
"""img/ に置いたカード画像の一覧（img/index.json）を作る。

置き方:  img/<シリーズID>/<カード番号>.<webp|jpg|jpeg|png>   例 img/M1L/091.webp, img/M6a/R.webp
        （30th は昔の img/135.webp のような直下置きも M6a として拾う）
出力:    {"M6a": {"135": "img/M6a/135.webp"}, "M1L": {"091": "img/M1L/091.webp"}}
画面はこの一覧を見て画像を出すので、置いていないカードに 404 を投げに行かなくなる。
"""
from __future__ import annotations
import json, pathlib, sys

IMG = pathlib.Path("img"); OUT = IMG / "index.json"
EXT = [".webp", ".jpg", ".jpeg", ".png"]        # 同じ番号で複数あればこの順で優先
LEGACY_SET = "M6a"                              # img/ 直下の番号ファイルはこのシリーズ扱い
SKIP = {"logo", "icon", "og", "index"}


def add(idx: dict, set_id: str, no: str, path: pathlib.Path):
    cur = idx.setdefault(set_id, {}).get(no)
    if cur and EXT.index(pathlib.Path(cur).suffix.lower()) <= EXT.index(path.suffix.lower()): return
    idx[set_id][no] = path.as_posix()


def main() -> int:
    if not IMG.is_dir(): print("img/ が無いので何もしません", file=sys.stderr); return 0
    idx: dict[str, dict[str, str]] = {}
    for f in sorted(IMG.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in EXT: continue
        if f.stem.lower() in SKIP: continue
        rel = f.relative_to(IMG).parts
        if len(rel) == 1: add(idx, LEGACY_SET, f.stem, f)                  # img/135.webp
        elif len(rel) == 2: add(idx, rel[0], f.stem, f)                    # img/M1L/091.webp
    OUT.write_text(json.dumps(idx, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"{OUT}: {sum(len(v) for v in idx.values())}枚 / {len(idx)}シリーズ → " +
          ", ".join(f"{k} {len(v)}枚" for k, v in sorted(idx.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
