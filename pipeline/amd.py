# -*- coding: utf-8 -*-
"""AMD 監控資料管線：Yahoo 日線與盤前盤後報價 → 算均線、MACD、量能、回補關卡、缺口、量價分布 → 寫 data/amd.json。

- 只用 requests（純 Python 計算），本機與 GitHub Actions 都能跑：python pipeline/amd.py
- 由 build.py 在大盤資料寫完後呼叫；失敗不影響大盤資料，沿用上次的 amd.json。
- 歷史情境（兩種情境、事件表、量能對照）是固定快照，放在 data/amd_static.json，不在這裡自動更新。
"""
from zoneinfo import ZoneInfo
import datetime as dt
import json
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "amd.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
TW = dt.timezone(dt.timedelta(hours=8))

SWING_HIGH_DATE = "2026-10-06"   # 回補關卡的高點日（盤中最高價），換波段時手動改
SWING_LOW_DATE = "2026-11-05"    # 回補關卡的低點日（盤中最低價）
RETRACE = (0.382, 0.5, 0.618, 0.786)
CHART_DAYS = 100                 # 走勢圖顯示的交易日數
VBP_START = "2026-05-06"         # 量價分布起算日（5/6 缺口當天）
GAP_SINCE = "2026-05-01"         # 缺口掃描起始日
VBP_BIN = 20                     # 量價分布每格寬度（美元）
LEVELS_ASOF = "2026-11-12"       # 手動關卡的整理日
# 手動維護的關鍵價位：換行情時更新 LEVELS_ASOF；均線與回補位由程式即時算
LEVELS = [
    {"cat": "壓力", "v": 658.52, "name": "658.5", "basis": "歷史高點（10/6 盤中最高）"},
    {"cat": "壓力", "v": 635, "name": "630–640", "basis": "9/25、10/2 高檔區（9/25 最高 639.00）", "lo": 630, "hi": 640},
    {"cat": "壓力", "v": 620, "name": "615–625", "basis": "9/21–9/22 的收盤與最高", "lo": 615, "hi": 625},
    {"cat": "壓力", "v": 606, "name": "605.5–606.2", "basis": "10/13 收盤 605.53、最高 606.20", "lo": 605.5, "hi": 606.2},
    {"cat": "壓力", "v": 600, "name": "600", "basis": "整數關卡；600–640 為 9–10 月成交的套牢區"},
    {"cat": "壓力", "v": 594, "name": "594.0", "basis": "11/12 最高"},
    {"cat": "支撐", "v": 583.5, "name": "582–585", "basis": "突破位：9 月缺口上緣 582.27、6/30 高點 584.73", "lo": 582.27, "hi": 584.73},
    {"cat": "支撐", "v": 568.5, "name": "567.7–569.3", "basis": "11/11 最高 567.65、11/12 開盤 569.28", "lo": 567.65, "hi": 569.28},
    {"cat": "支撐", "v": 554, "name": "553–555", "basis": "SMA50、11/12 最低 554.90、11/11 收盤 552.90", "lo": 552.9, "hi": 554.9},
    {"cat": "支撐", "v": 539, "name": "539", "basis": "季線（SMA60）"},
    {"cat": "支撐", "v": 529, "name": "519–539", "basis": "匯集區：月線、半年線、SMA100、50% 回補位、10/30 缺口下緣 520.40", "lo": 519, "hi": 539},
    {"cat": "支撐", "v": 500, "name": "500", "basis": "38.2% 回補位 500.05；11/10 最低 495"},
    {"cat": "支撐", "v": 464, "name": "460–468", "basis": "11/9 向上缺口 459.80–468.21 與 6–8 月低點", "lo": 459.8, "hi": 468.21},
    {"cat": "支撐", "v": 398, "name": "393–402", "basis": "5 月缺口上緣 402.04、11/5 最低 402.10", "lo": 393, "hi": 402.1},
]


def daily(sym, rng="2y"):
    """回傳 (日線列 [{d,o,h,l,c,v}], 是否盤中, 最新成交時間)。日期為交易所當地日期。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(sym)}?range={rng}&interval=1d"
    r = requests.get(url, headers=UA, timeout=40)
    r.raise_for_status()
    j = r.json()["chart"]["result"][0]
    m, q, off = j["meta"], j["indicators"]["quote"][0], j["meta"].get("gmtoffset", 0)
    rows = {}
    for i, t in enumerate(j["timestamp"]):
        o, h, l, c, v = (q[k][i] for k in ("open", "high", "low", "close", "volume"))
        if None in (o, h, l, c):
            continue
        d = dt.datetime.fromtimestamp(t + off, dt.timezone.utc).strftime("%Y-%m-%d")
        rows[d] = {"d": d, "o": o, "h": h, "l": l, "c": c, "v": v or 0}
    out = [rows[d] for d in sorted(rows)]
    per, now = (m.get("currentTradingPeriod") or {}).get("regular") or {}, time.time()
    live = bool(per) and per["start"] <= now < per["end"] and out[-1]["d"] == dt.datetime.fromtimestamp(now + off, dt.timezone.utc).strftime("%Y-%m-%d")
    return out, live, m.get("regularMarketTime")


def extended(sym):
    """最新一筆含盤前盤後的 5 分 K：回傳 (價, 時間, 時段)。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(sym)}?range=1d&interval=5m&includePrePost=true"
    r = requests.get(url, headers=UA, timeout=40)
    r.raise_for_status()
    j = r.json()["chart"]["result"][0]
    bars = [(t, c) for t, c in zip(j["timestamp"], j["indicators"]["quote"][0]["close"]) if c is not None]
    if not bars:
        return None
    t, c = bars[-1]
    hm = dt.datetime.fromtimestamp(t, ZoneInfo("America/New_York")).strftime("%H:%M")
    return c, t, ("盤前" if hm < "09:30" else "盤後" if hm >= "16:00" else "正常盤")


def sma(v, n):
    return [None if i + 1 < n else sum(v[i + 1 - n:i + 1]) / n for i in range(len(v))]


def ema(v, n):
    k, out, e = 2 / (n + 1), [], None
    for x in v:
        e = x if e is None else x * k + e * (1 - k)
        out.append(e)
    return out


def r2(x, d=2):
    return None if x is None else round(x, d)


def build():
    rows, live, mtime = daily("AMD")
    if len(rows) < 260:
        raise RuntimeError(f"AMD 日線只有 {len(rows)} 筆")
    C = [x["c"] for x in rows]
    V = [x["v"] / 1e6 for x in rows]
    last, prev = rows[-1], rows[-2]
    n = len(rows)
    status = {"Yahoo": {"ok": True, "asof": last["d"], "err": None}}

    # ---- 報價
    quote = {"date": last["d"], "live": live, "open": r2(last["o"]), "high": r2(last["h"]), "low": r2(last["l"]), "close": r2(last["c"]),
             "prev": r2(prev["c"]), "chg": r2((last["c"] / prev["c"] - 1) * 100), "vol": r2(V[-1], 1), "ext": None}
    if not live:
        try:
            e = extended("AMD")
            if e and e[2] != "正常盤":
                quote["ext"] = {"price": r2(e[0]), "chg": r2((e[0] / last["c"] - 1) * 100), "session": e[2], "time": e[1]}
        except Exception as ex:
            print("AMD 盤前盤後失敗：", ex)

    # ---- 回補關卡（盤中高低點）
    hi_row = next(x for x in rows if x["d"] == SWING_HIGH_DATE)
    lo_row = next(x for x in rows if x["d"] == SWING_LOW_DATE)
    hi, lo = hi_row["h"], lo_row["l"]
    cur = last["c"]
    swing = {"high": {"date": hi_row["d"], "v": r2(hi)}, "low": {"date": lo_row["d"], "v": r2(lo)},
             "drop": r2((lo / hi - 1) * 100, 1), "retrace": r2((cur - lo) / (hi - lo) * 100, 1),
             "fromHigh": r2((cur / hi - 1) * 100, 1), "fromLow": r2((cur / lo - 1) * 100, 1),
             "levels": [{"name": f"{p * 100:.1f}%", "v": r2(lo + p * (hi - lo)), "hit": cur >= lo + p * (hi - lo)} for p in RETRACE]}

    # ---- 均線與乖離
    mas = []
    for nm, kind, k in [("月線 SMA20", "s", 20), ("SMA50", "s", 50), ("季線 SMA60", "s", 60), ("SMA100", "s", 100), ("半年線 SMA120", "s", 120), ("年線 SMA240", "s", 240)]:
        s = sma(C, k)
        streak = 0
        for i in range(n - 1, -1, -1):
            if s[i] is not None and C[i] > s[i]:
                streak += 1
            else:
                break
        mas.append({"name": nm, "n": k, "v": r2(s[-1]), "d5": r2(s[-1] - s[-6]), "bias": r2((cur / s[-1] - 1) * 100, 1), "above": cur > s[-1], "streak": streak})
    series_ma = {f"sma{k}": sma(C, k) for k in (20, 50, 100, 200)}

    # ---- 量能
    v10, v60, v250 = sum(V[-10:]) / 10, sum(V[-60:]) / 60, sum(V[-250:]) / 250
    state = "量增" if v10 / v60 > 1.2 else "量縮" if v10 / v60 < 0.8 else "量平"
    days = []
    for i in range(n - 10, n):
        base = sum(V[i - 20:i]) / 20
        days.append({"d": rows[i]["d"], "v": r2(V[i], 1), "chg": r2((C[i] / C[i - 1] - 1) * 100), "vr": r2(V[i] / base)})
    volume = {"v10": r2(v10, 1), "v60": r2(v60, 1), "v250": r2(v250, 1), "r60": r2(v10 / v60), "r250": r2(v10 / v250), "state": state,
              "lowThr": r2(v60 * .8, 1), "highThr": r2(v60 * 1.2, 1), "days": days}

    # ---- MACD
    e12, e26 = ema(C, 12), ema(C, 26)
    line = [a - b for a, b in zip(e12, e26)]
    sig = ema(line, 9)
    hist = [a - b for a, b in zip(line, sig)]
    cross = None
    for i in range(n - 1, 0, -1):
        if (hist[i] > 0) != (hist[i - 1] > 0):
            cross = {"date": rows[i]["d"], "dir": "黃金交叉" if hist[i] > 0 else "死亡交叉"}
            break
    zero = None
    for i in range(n - 1, 0, -1):
        if (line[i] > 0) != (line[i - 1] > 0):
            zero = {"date": rows[i]["d"], "dir": "翻上零軸" if line[i] > 0 else "跌破零軸"}
            break
    macd = {"line": r2(line[-1]), "signal": r2(sig[-1]), "hist": r2(hist[-1]), "cross": cross, "zero": zero,
            "series": [[rows[i]["d"], r2(line[i]), r2(sig[i]), r2(hist[i])] for i in range(n - 60, n)]}

    # ---- 缺口（未回補）
    gaps = []
    for i in range(1, n):
        if rows[i]["d"] < GAP_SINCE:
            continue
        a, b = rows[i - 1], rows[i]
        if b["l"] > a["h"] and not any(x["l"] <= a["h"] for x in rows[i + 1:]):
            gaps.append({"type": "向上", "lo": r2(a["h"]), "hi": r2(b["l"]), "from": a["d"], "to": b["d"]})
        if b["h"] < a["l"] and not any(x["h"] >= a["l"] for x in rows[i + 1:]):
            gaps.append({"type": "向下", "lo": r2(b["h"]), "hi": r2(a["l"]), "from": a["d"], "to": b["d"]})
    # 5/5→5/6 的缺口以 5/6 開盤跳空，上面的掃描會涵蓋；排序由新到舊
    gaps.sort(key=lambda g: g["to"], reverse=True)

    # ---- 量價分布
    sub = [x for x in rows if x["d"] >= VBP_START]
    top = int(max(x["h"] for x in sub) // VBP_BIN * VBP_BIN)
    bot = int(min(x["l"] for x in sub) // VBP_BIN * VBP_BIN)
    acc = {b: 0.0 for b in range(bot, top + VBP_BIN, VBP_BIN)}
    for x in sub:
        span = x["h"] - x["l"] or 1e-9
        for b in acc:
            a_, z_ = max(x["l"], b), min(x["h"], b + VBP_BIN)
            if z_ > a_:
                acc[b] += x["v"] * (z_ - a_) / span / 1e8
    tot = sum(acc.values())
    vbp = {"start": VBP_START, "total": r2(tot), "bins": [{"lo": b, "hi": b + VBP_BIN, "v": r2(acc[b], 2), "pct": r2(acc[b] / tot * 100, 1)} for b in sorted(acc, reverse=True) if acc[b] > 0.005]}

    # ---- 走勢圖資料
    start = n - CHART_DAYS
    chart = {"candles": [[x["d"], r2(x["o"]), r2(x["h"]), r2(x["l"]), r2(x["c"]), r2(x["v"] / 1e6, 1)] for x in rows[start:]],
             **{k: [r2(v) for v in s[start:]] for k, s in series_ma.items()}}

    # ---- 動能數字
    gain5 = (C[-1] / C[-6] - 1) * 100
    hi60 = max(C[-61:-1])
    stats = {"gain5": r2(gain5, 1), "from60High": r2((cur / hi60 - 1) * 100, 1), "gain15": r2((C[-1] / C[-16] - 1) * 100, 1)}

    # ---- 板塊：SOX
    sox = None
    try:
        sr, _, _ = daily("^SOX")
        sc = [x["c"] for x in sr]
        sdate = {x["d"]: x["c"] for x in sr}
        base = sdate.get(SWING_LOW_DATE)
        sox = {"date": sr[-1]["d"], "close": r2(sc[-1]), "chg": r2((sc[-1] / sc[-2] - 1) * 100),
               "sma20": r2(sum(sc[-20:]) / 20), "sma50": r2(sum(sc[-50:]) / 50), "sma200": r2(sum(sc[-200:]) / 200),
               "sinceLow": r2((sc[-1] / base - 1) * 100, 1) if base else None, "amdSinceLow": r2((cur / lo_row["c"] - 1) * 100, 1)}
        status["SOX"] = {"ok": True, "asof": sr[-1]["d"], "err": None}
    except Exception as ex:
        print("SOX 失敗：", ex)
        status["SOX"] = {"ok": False, "asof": None, "err": str(ex)[:120]}

    levels = []
    for lv in LEVELS:
        levels.append({**lv, "dist": r2((lv["v"] / cur - 1) * 100, 1)})

    return {"updated": dt.datetime.now(TW).strftime("%Y/%m/%d %H:%M"), "status": status, "quote": quote, "stats": stats, "swing": swing,
            "mas": mas, "volume": volume, "macd": macd, "gaps": gaps, "vbp": vbp, "chart": chart, "sox": sox,
            "levels": levels, "levelsAsof": LEVELS_ASOF}


def main():
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else None
    try:
        data = build()
    except Exception as e:
        print("ERR AMD", e)
        if old:
            old["status"] = {"Yahoo": {"ok": False, "asof": (old.get("quote") or {}).get("date"), "err": str(e)[:160]}}
            OUT.write_text(json.dumps(old, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        return
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    q = data["quote"]
    print("AMD", q["date"], q["close"], f'{q["chg"]:+.2f}%', "量能", data["volume"]["state"], "回補", data["swing"]["retrace"], "%")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
