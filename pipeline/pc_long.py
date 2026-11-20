# -*- coding: utf-8 -*-
"""Put/Call 長期走勢（2017 起）＋標普 500＋暴跌區間 → data/pc_long.json。
P/C：data/pc_long_base.json（2016/12–2024/2 凍結）＋ data/pc_history.json（2024/3 起，build.py 每天併入）。
暴跌區間：標普收盤 zigzag，跌幅與反彈幅都 ≥7% 才算轉折（與 宏觀因果驗證/putcall/crash/events.py 同規則）。"""
import datetime as dt, json, time
from pathlib import Path
import requests
ROOT = Path(__file__).resolve().parent.parent
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
START, ZZ = "2017-01-01", 0.07


def spx():
    j = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?period1=1451606400&period2={int(time.time())}&interval=1d",
                     headers=UA, timeout=60).json()["chart"]["result"][0]
    off = j["meta"].get("gmtoffset", 0); q = j["indicators"]["quote"][0]["close"]
    out = {dt.datetime.fromtimestamp(t + off, dt.timezone.utc).strftime("%Y-%m-%d"): c for t, c in zip(j["timestamp"], q) if c}
    m = j["meta"]   # 最新一根收盤偶爾整批 null，用 regularMarketPrice 補
    if m.get("regularMarketPrice") and m.get("regularMarketTime"):
        d = dt.datetime.fromtimestamp(m["regularMarketTime"] + off, dt.timezone.utc).strftime("%Y-%m-%d")
        out.setdefault(d, m["regularMarketPrice"])
    return dict(sorted(out.items()))


def zigzag(px, r):
    ds, vs = list(px), list(px.values()); piv = []; trend = 0; hi = lo = 0
    for i in range(1, len(vs)):
        if vs[i] > vs[hi]: hi = i
        if vs[i] < vs[lo]: lo = i
        if trend >= 0 and vs[i] <= vs[hi] * (1 - r):
            piv.append(("H", hi)); trend = -1; lo = i
        elif trend <= 0 and vs[i] >= vs[lo] * (1 + r):
            if trend == -1: piv.append(("L", lo))
            trend = 1; hi = i
    if trend == -1: piv.append(("L", lo))   # 最後一段仍在跌：低點暫定為目前最低
    return [[ds[i], ds[j], round(vs[j] / vs[i] - 1, 4), k == len(piv) - 1 and trend == -1]
            for k, ((a, i), (b, j)) in enumerate(zip(piv, piv[1:]), 1) if a == "H" and b == "L"]


def main():
    pc = json.loads((ROOT / "data" / "pc_long_base.json").read_text(encoding="utf-8"))["data"]
    for d, v in json.loads((ROOT / "data" / "pc_history.json").read_text(encoding="utf-8"))["cboe"].items():
        if v.get("total"): pc[d] = [v.get("total"), v.get("equity"), v.get("index")]
    px = spx(); ds = sorted(pc); s, last = [], None
    for d in ds:
        last = px.get(d, last); s.append(round(last, 2) if last else None)
    ev = [e for e in zigzag(px, ZZ) if e[1] >= START]
    out = {"updated": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y/%m/%d %H:%M"), "start": START,
           "d": ds, "t": [pc[d][0] for d in ds], "e": [pc[d][1] for d in ds], "i": [pc[d][2] for d in ds], "s": s, "ev": ev}
    (ROOT / "data" / "pc_long.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print("pc_long", len(ds), ds[-1], "events", len(ev))


if __name__ == "__main__":
    main()
