# -*- coding: utf-8 -*-
"""回補走勢子頁資料管線（聯發科、博通）：Yahoo 日線 → 低點之後每日收盤與量 → data/<key>.json。

- 格式與 amd.json 的 swing 區塊一致，頁面沿用 retrace.js 畫圖。
- 高低點日期依使用者定案的「回補關卡一律以 10/6 為高點」；低點取高點之後的盤中最低價所在日。
  換波段時手動改下面 STOCKS 的 high / low 日期。
- 由 build.py 在 amd.py 之後呼叫；失敗只沿用上次檔案，不影響大盤資料。
"""
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import requests  # noqa: E402
from amd import daily, ema, r2, RETRACE, TW, UA  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STOCKS = [
    {"key": "mediatek", "sym": "2454.TW", "name": "聯發科", "en": "MediaTek", "code": "2454", "high": "2026-10-06", "low": "2026-11-06", "dec": 0, "ccy": "TWD"},
    {"key": "avgo", "sym": "AVGO", "name": "博通", "en": "Broadcom", "code": "AVGO", "high": "2026-10-06", "low": "2026-11-06", "dec": 2, "ccy": "USD"},
    # ETF 監控子頁（etf.html）四檔；低點日期手動設定（高點之後盤中最低價所在日）
    {"key": "etf_0050", "sym": "0050.TW", "name": "元大台灣50", "en": "Yuanta Taiwan 50 ETF", "code": "0050", "high": "2026-10-06", "low": "2026-11-06", "dec": 2, "ccy": "TWD", "close": True, "vpvr": 0.5},
    {"key": "etf_soxx", "sym": "SOXX", "name": "iShares 半導體 ETF", "en": "iShares Semiconductor ETF", "code": "SOXX", "high": "2026-10-06", "low": "2026-11-05", "dec": 2, "ccy": "USD", "close": True},
    {"key": "etf_qqq", "sym": "QQQ", "name": "Invesco 那斯達克100 ETF", "en": "Invesco QQQ Trust", "code": "QQQ", "high": "2026-10-06", "low": "2026-11-05", "dec": 2, "ccy": "USD", "close": True},
    {"key": "etf_spy", "sym": "SPY", "name": "SPDR 標普500 ETF", "en": "SPDR S&P 500 ETF", "code": "SPY", "high": "2026-10-06", "low": "2026-11-05", "dec": 2, "ccy": "USD", "close": True},
]


def vpvr(sym, start, lo, hi, step):
    """VPVR（可視範圍成交量分布）：取低點日起的 15 分 K，每根 K 的量平均攤到它的 低~高 價格格內。
    回傳 {bins:[[格下緣,格上緣,量(百萬股)]], poc, vah, val, src}；價值區＝由 POC 向外擴到涵蓋 70% 成交量。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(sym)}?range=1mo&interval=15m"
    r = requests.get(url, headers=UA, timeout=40)
    r.raise_for_status()
    j = r.json()["chart"]["result"][0]
    q, off = j["indicators"]["quote"][0], j["meta"].get("gmtoffset", 0)
    nb = int(round((hi - lo) / step)) + 1
    acc = [0.0] * nb
    for i, t in enumerate(j["timestamp"]):
        h, l, v = q["high"][i], q["low"][i], q["volume"][i]
        if None in (h, l) or not v:
            continue
        if dt.datetime.fromtimestamp(t + off, dt.timezone.utc).strftime("%Y-%m-%d") < start:
            continue
        a, z = int((l - lo) // step), int((h - lo) // step)   # 低於圖軸底（收盤低點）的格子不畫，但量照比例攤，只留畫面內的
        for b in range(max(a, 0), min(z, nb - 1) + 1):
            acc[b] += v / (z - a + 1) / 1e6
    tot = sum(acc)
    if tot <= 0:
        raise ValueError("vpvr 無量")
    poc = max(range(nb), key=lambda b: acc[b])
    a = z = poc
    got = acc[poc]
    while got < tot * 0.7 and (a > 0 or z < nb - 1):
        up = acc[z + 1] if z < nb - 1 else -1
        dn = acc[a - 1] if a > 0 else -1
        if up >= dn:
            z += 1; got += up
        else:
            a -= 1; got += dn
    bins = [[r2(lo + b * step), r2(lo + (b + 1) * step), r2(acc[b], 2)] for b in range(nb) if acc[b] > 0]
    return {"step": step, "total": r2(tot, 1), "bins": bins, "poc": r2(lo + (poc + .5) * step), "val": r2(lo + a * step), "vah": r2(lo + (z + 1) * step), "src": "15m", "start": start}


def build(s):
    rows, live, _ = daily(s["sym"])
    rows = [x for x in rows if not (x["v"] == 0 and x["h"] == x["l"])]   # 休市日的假資料（Yahoo 偶爾會補一筆）
    V = [x["v"] / 1e6 for x in rows]
    hi_row = next(x for x in rows if x["d"] == s["high"])
    lo_row = next(x for x in rows if x["d"] == s["low"])
    hi, lo = (hi_row["c"], lo_row["c"]) if s.get("close") else (hi_row["h"], lo_row["l"])   # close=True：高低點用收盤價（ETF 子頁，與大盤頁一致）
    cur = rows[-1]["c"]
    li = rows.index(lo_row)
    C = [x["c"] for x in rows]
    line = [a - b for a, b in zip(ema(C, 12), ema(C, 26))]
    sig = ema(line, 9)
    macd = [[rows[i]["d"], r2(line[i]), r2(sig[i]), r2(line[i] - sig[i])] for i in range(li, len(rows))]
    swing = {"high": {"date": hi_row["d"], "v": r2(hi)}, "low": {"date": lo_row["d"], "v": r2(lo)},
             "drop": r2((lo / hi - 1) * 100, 1), "retrace": r2((cur - lo) / (hi - lo) * 100, 1),
             "macd": macd, "lowVol": r2(V[li], 1), "lowChg": r2((lo_row["c"] / rows[li - 1]["c"] - 1) * 100),
             "path": [[x["d"], r2(x["c"]), r2(V[i], 1), r2((x["c"] / rows[i - 1]["c"] - 1) * 100)] for i, x in enumerate(rows) if x["d"] > s["low"]],
             "levels": [{"name": f"{p * 100:.1f}%", "v": r2(lo + p * (hi - lo)), "hit": cur >= lo + p * (hi - lo)} for p in RETRACE]}
    if s.get("vpvr"):
        try:
            swing["vp"] = vpvr(s["sym"], s["low"], lo, hi, s["vpvr"])
        except Exception as e:
            print("ERR vpvr", s["key"], e)
    return {"lowWord": "收盤低" if s.get("close") else "最低", "updated": dt.datetime.now(TW).strftime("%Y/%m/%d %H:%M"), "name": s["name"], "en": s["en"], "code": s["code"],
            "dec": s["dec"], "asof": rows[-1]["d"], "live": live, "swing": swing,
            "status": {"Yahoo": {"ok": True, "asof": rows[-1]["d"], "err": None}}}


def main():
    for s in STOCKS:
        out = ROOT / "data" / f"{s['key']}.json"
        try:
            d = build(s)
        except Exception as e:
            print("ERR", s["key"], e)
            if out.exists():
                old = json.loads(out.read_text(encoding="utf-8"))
                old["status"] = {"Yahoo": {"ok": False, "asof": old.get("asof"), "err": str(e)[:160]}}
                out.write_text(json.dumps(old, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            continue
        out.write_text(json.dumps(d, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(s["key"], d["asof"], d["swing"]["retrace"], "%")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
