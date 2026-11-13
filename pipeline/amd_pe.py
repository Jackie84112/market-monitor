# -*- coding: utf-8 -*-
"""AMD Non-GAAP 本益比（trailing）：日 K 線 ÷ TTM Non-GAAP EPS → data/amd_pe.json

- EPS 是手動維護的表（來源：各季 8-K 財報新聞稿 Non-GAAP 稀釋 EPS 對帳表）。出新財報時在 EPS 加一列：(季別, EPS, 8-K 申報日)。
- TTM EPS = 最近四季 Non-GAAP EPS 加總；財報申報日為盤後，所以「下一個交易日」起才套用新的 TTM（避免用到當時市場還不知道的數字）。
- 價格用 Yahoo 日線（未還原股利，AMD 不配息，等同原始價）。由 amd.py 結尾呼叫，也可單獨跑：python pipeline/amd_pe.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "amd_pe.json"

# (日曆季, Non-GAAP 稀釋 EPS, 8-K 申報日＝盤後公布日)；22Q4 取自 23Q4 8-K 的去年同季欄
EPS = [
    ("22Q4", 0.69, "2023-01-31"), ("23Q1", 0.60, "2023-05-02"), ("23Q2", 0.58, "2023-08-01"), ("23Q3", 0.70, "2023-10-31"),
    ("23Q4", 0.77, "2024-01-30"), ("24Q1", 0.62, "2024-04-30"), ("24Q2", 0.69, "2024-07-30"), ("24Q3", 0.92, "2024-10-29"),
    ("24Q4", 1.09, "2025-02-04"), ("25Q1", 0.96, "2025-05-06"), ("25Q2", 0.48, "2025-08-05"), ("25Q3", 1.20, "2025-11-04"),
    ("25Q4", 1.53, "2026-02-03"), ("26Q1", 1.37, "2026-05-05"), ("26Q2", 1.66, "2026-08-04"), ("26Q3", 2.09, "2026-11-03"),
]
START = "2023-11-01"   # 第一個有完整四季 TTM 的日期（23Q3 公布 10/31 之後）


def build(rows):
    ttm = []   # (生效日, TTM EPS, 季別)
    for i in range(3, len(EPS)):
        ttm.append((EPS[i][2], round(sum(e[1] for e in EPS[i - 3:i + 1]), 2), EPS[i][0]))
    cand, pe, eps = [], [], []
    for r in rows:
        if r["d"] < START:
            continue
        # 申報日盤後公布 → 申報日當天仍用舊 TTM（日期嚴格大於申報日才套用）
        cur = [t for t in ttm if t[0] < r["d"]][-1]
        cand.append([r["d"], round(r["o"], 2), round(r["h"], 2), round(r["l"], 2), round(r["c"], 2)])
        eps.append(cur[1])
        pe.append(round(r["c"] / cur[1], 2))
    return {
        "candles": cand, "pe": pe, "ttm": eps,
        "eps": [{"q": q, "eps": e, "date": d} for q, e, d in EPS],
        "releases": [{"date": t[0], "q": t[2], "ttm": t[1]} for t in ttm if t[0] >= START],
        "asof": cand[-1][0],
    }


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from amd import daily
    rows, _, _ = daily("AMD", "5y")
    data = build(rows)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    p = data["pe"]
    print("AMD PE", data["asof"], "收盤", data["candles"][-1][4], "TTM", data["ttm"][-1], "PE", p[-1], "區間", min(p), max(p), len(p), "天")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
