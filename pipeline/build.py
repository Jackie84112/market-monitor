# -*- coding: utf-8 -*-
"""大盤監控資料管線：抓各來源 → 算關卡與方向 → 寫 data/monitor.json。

- 每個來源獨立容錯：抓失敗就沿用上次的值，並記到 status 讓頁面標示。
- 每日逐筆才查得到的來源（Cboe、證交所、期交所）累積在 data/store.json，只補缺的日期。
- 只用 requests，本機與 GitHub Actions 都能跑：python pipeline/build.py [--backfill 天數]
"""
from zoneinfo import ZoneInfo
import csv
import datetime as dt
import html
import io
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT, STORE = ROOT / "data" / "monitor.json", ROOT / "data" / "store.json"
PC_HIST = ROOT / "data" / "pc_history.json"   # Put/Call 長歷史（2024/3 起），供事件對照算百分位
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
TW = dt.timezone(dt.timedelta(hours=8))
TWSE_DELAY = 1.5   # 證交所限流，勿低於 1.4 秒
KEEP = 180         # 每條序列保留的筆數
PEAK_DATE = "2026-10-06"    # 回補關卡統一起算的高點日（換波段時手動改）
CHART_START = "2026-06-01"  # 指數走勢圖起始日
RETRACE = (0.382, 0.5, 0.618)
# Put/Call 事件對照：最後一個是本次（頁面以強調色畫），新增事件往後加
PC_EVENTS = [("川普關稅", "2025-04-08"), ("Burry 放空", "2025-11-20"), ("美伊戰爭", "2026-03-30"),
             ("去槓桿", "2026-07-29"), ("CDS＋民主黨勝選", "2026-11-05")]
PC_WIN = (-5, 10)   # 事件日前 5、後 10 個交易日
PC_LOOKBACK = 252   # 百分位：與前 252 個交易日（約一年）比

INDICES = [("spx", "S&P 500", "^GSPC"), ("ndx", "Nasdaq-100", "^NDX"), ("sox", "費城半導體 SOX", "^SOX"),
           ("dji", "道瓊工業", "^DJI"), ("t0050", "元大台灣 50（0050）", "0050.TW"), ("kospi", "韓國 KOSPI", "^KS11")]
FUTURES = [("es", "S&P 500 期貨", "ES=F"), ("nq", "Nasdaq-100 期貨", "NQ=F"), ("ym", "道瓊期貨", "YM=F"), ("soxf", "費城半導體 SOX 期貨", "SOX=F")]
BOND_ETF = [("b00679", "00679B 元大美債 20 年", "00679B.TWO"), ("b00687", "00687B 國泰 20 年美債", "00687B.TWO"),
            ("b00720", "00720B 元大投資級公司債", "00720B.TWO"), ("b00937", "00937B 群益 ESG 投等債 20+", "00937B.TWO")]
OTHER_YAHOO = {"vix": "^VIX", "vix3m": "^VIX3M", "rsp": "RSP", "spy": "SPY", "tsm": "TSM", "t2330": "2330.TW", "usdtwd": "USDTWD=X"}
FRED = {"oas_hy": "BAMLH0A0HYM2", "oas_ig": "BAMLC0A0CM"}

status = {}


def note(src, ok, asof=None, err=None):
    status[src] = {"ok": ok, "asof": asof, "err": str(err)[:160] if err else None}


def num(s):
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return None


# ---------------------------------------------------------------- Yahoo
def yahoo(sym, adjusted=False):
    """回傳 (序列 [[日期, 值]...], 是否盤中, 最新成交時間)。日期為交易所當地日期。"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(sym)}?range=1y&interval=1d"
    r = requests.get(url, headers=UA, timeout=40)
    r.raise_for_status()
    j = r.json()["chart"]["result"][0]
    m = j["meta"]
    q = j["indicators"]["quote"][0]["close"]
    adj = (j["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(q)
    off = m.get("gmtoffset", 0)
    out = {}
    for t, c, a in zip(j["timestamp"], q, adj):
        v = a if adjusted and a is not None else c
        if v is not None:
            out[dt.datetime.fromtimestamp(t + off, dt.timezone.utc).strftime("%Y-%m-%d")] = v
    rows = [[d, v] for d, v in sorted(out.items())]
    per, now = (m.get("currentTradingPeriod") or {}).get("regular") or {}, time.time()
    live = bool(per) and per["start"] <= now < per["end"] and rows[-1][0] == dt.datetime.fromtimestamp(now + off, dt.timezone.utc).strftime("%Y-%m-%d")
    return rows, live, m.get("regularMarketTime")


def intraday(sym, prepost=False, gap=2.25 * 3600):
    """15 分 K 走勢與最新一筆報價：從前一次美股收盤（15:45 那根收在 16:00 ET）到最新。
    gap＝最新報價距收盤至少多久才換用該次收盤；期貨 18:00 ET 才開新盤，所以預設 2.25 小時。回傳 (走勢, 最新價, 最新時間)。"""
    flag = "true" if prepost else "false"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(sym)}?range=5d&interval=15m&includePrePost={flag}"
    r = requests.get(url, headers=UA, timeout=40)
    r.raise_for_status()
    j = r.json()["chart"]["result"][0]
    bars = [(t, c) for t, c in zip(j["timestamp"], j["indicators"]["quote"][0]["close"]) if c is not None]
    if not bars:
        return [], None, None
    last_t, et = bars[-1][0], ZoneInfo("America/New_York")
    day, start = dt.datetime.fromtimestamp(last_t, et).date(), None
    for i in range(8):
        d = day - dt.timedelta(days=i)
        t = dt.datetime(d.year, d.month, d.day, 15, 45, tzinfo=et).timestamp()
        if d.weekday() < 5 and last_t - t >= gap:
            start = t
            break
    path = [[dt.datetime.fromtimestamp(t, TW).strftime("%m-%d %H:%M"), round(c, 2)] for t, c in bars if start is not None and t >= start]
    return path, bars[-1][1], last_t


def us_session(ts):
    t = dt.datetime.fromtimestamp(ts, ZoneInfo("America/New_York")).strftime("%H:%M")
    return "盤前" if t < "09:30" else "盤後" if t >= "16:00" else "正常盤"


def taifex_txf():
    """台指期近月：期交所報價接口，日盤（-F）與夜盤（-M）合併。夜盤過午夜仍記開盤日，時間早於 15:00 要加一天。"""
    head = {**UA, "Content-Type": "application/json;charset=UTF-8", "Origin": "https://mis.taifex.com.tw", "Referer": "https://mis.taifex.com.tw/futures/"}
    api = lambda ep, body: requests.post(f"https://mis.taifex.com.tw/futures/api/{ep}", json=body, headers=head, timeout=30).json()["RtData"]
    sessions = []
    for market, night in (("0", False), ("1", True)):
        quotes = api("getQuoteList", {"MarketType": market, "SymbolType": "F", "KindID": "1", "CID": "TXF", "ExpireMonth": "", "RowSize": "3", "PageNo": "", "SortColumn": "", "AscDesc": "A"})["QuoteList"]
        q = next((x for x in quotes if re.fullmatch(r"TXF[A-Z]\d-[FM]", x.get("SymbolID", "")) and x.get("CLastPrice") and x.get("CTime")), None)
        if not q:
            continue
        base = dt.datetime.strptime(q["CDate"], "%Y%m%d").replace(tzinfo=TW)

        def stamp(hhmmss, base=base, night=night):
            h, m = int(hhmmss[:2]), int(hhmmss[2:4])     # 接口會出現 046000 這種寫法，用加法進位
            return base + dt.timedelta(days=1 if night and h < 15 else 0, hours=h, minutes=m, seconds=int(hhmmss[4:6] or 0))

        chart = api("getChartData1M", {"SymbolID": q["SymbolID"]})
        bars = next((v for v in chart.values() if isinstance(v, list) and v and isinstance(v[0], list)), [])
        sessions.append({"night": night, "ref": float(q["CRefPrice"]), "last": float(q["CLastPrice"]), "time": stamp(q["CTime"]),
                         "bars": [(stamp(b[0]), float(b[4])) for b in bars if b[4]]})
    if not sessions:
        raise ValueError("期交所未回傳台指期報價")
    sessions.sort(key=lambda x: x["time"])
    cur = sessions[-1]
    # 同一結算價底下的夜盤＋日盤接成一條線；新夜盤開始後只畫新夜盤
    bars = sorted((b for x in sessions if x is cur or x["ref"] == cur["ref"] for b in x["bars"]), key=lambda b: b[0])
    thin = [b for i, b in enumerate(bars) if i % 15 == 0 or i == len(bars) - 1]
    return {"key": "txf_q", "name": "台指期（近月）", "last": cur["last"], "chg": round((cur["last"] / cur["ref"] - 1) * 100, 2), "time": int(cur["time"].timestamp()), "digits": 0,
            "line": [[t.strftime("%m-%d %H:%M"), v] for t, v in thin], "base": cur["ref"], "extra": "夜盤" if cur["night"] else "日盤"}


# ---------------------------------------------------------------- FRED／財政部
def fred(series_id):
    # FRED 不要帶瀏覽器 UA
    r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={(dt.date.today() - dt.timedelta(days=400))}", timeout=60)
    r.raise_for_status()
    return [[row[0], num(row[1]) * 100] for row in list(csv.reader(io.StringIO(r.text)))[1:] if len(row) > 1 and num(row[1]) is not None]


def treasury():
    year = dt.date.today().year
    rows = {}
    for y in (year - 1, year):
        url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
               f"daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        for row in csv.DictReader(io.StringIO(r.text)):
            d = dt.datetime.strptime(row["Date"], "%m/%d/%Y").strftime("%Y-%m-%d")
            rows[d] = (num(row["2 Yr"]), num(row["10 Yr"]))
    days = sorted(rows)
    return [[d, rows[d][0]] for d in days if rows[d][0] is not None], [[d, rows[d][1]] for d in days if rows[d][1] is not None]


# ---------------------------------------------------------------- 逐日來源
def twse(path, **params):
    r = requests.get(f"https://www.twse.com.tw/rwd/zh/{path}", params={**params, "response": "json"}, headers=UA, timeout=40)
    time.sleep(TWSE_DELAY)
    r.raise_for_status()
    return r.json()


def twse_flows(ymd):
    j = twse("fund/BFI82U", type="day", dayDate=ymd)
    if j.get("stat") != "OK" or not j.get("data"):
        return None
    amt = {row[0]: num(row[3]) / 1e8 for row in j["data"]}
    # 用開頭比對：「外資及陸資(不含外資自營商)」也含「自營商」三字，不能用包含判斷
    pick = lambda head: round(sum(v for k, v in amt.items() if k.startswith(head)), 1)
    return {"fi": pick("外資"), "it": pick("投信"), "de": pick("自營商")}


def twse_breadth_margin(ymd):
    """上市股票漲跌家數；融資金額與維持率（凱基口徑：Σ融資張×收盤×1000÷融資金額，含 ETF）。融資晚間才公布，先拿到的先存。"""
    res = {}
    jp = twse("afterTrading/MI_INDEX", date=ymd, type="ALLBUT0999")
    if jp.get("stat") != "OK":
        return res
    close = {}
    for t in jp.get("tables", []):
        f = t.get("fields") or []
        if "漲跌" in (t.get("title") or "") and t.get("data"):
            cnt = {row[0][:2]: int(re.sub(r"\D", "", row[2].split("(")[0]) or 0) for row in t["data"]}
            res["up"], res["down"] = cnt.get("上漲"), cnt.get("下跌")
        if "收盤價" in f and "證券代號" in f:
            fi, ci = f.index("收盤價"), f.index("證券代號")
            for row in t["data"]:
                c = num(row[fi])
                if c:
                    close[row[ci].strip()] = c
    jm = twse("marginTrading/MI_MARGN", date=ymd, selectType="ALL")
    tabs = jm.get("tables") or []
    if jm.get("stat") == "OK" and len(tabs) >= 2 and tabs[1].get("data") and close:
        fin = next((num(r[5]) * 1000 for r in tabs[0]["data"] if "融資金額" in r[0]), None)
        fields = tabs[1]["fields"]
        bi = 6 if fields[6] == "今日餘額" else fields.index("今日餘額")
        mv = sum((num(r[bi]) or 0) * 1000 * close.get(r[0].strip(), 0) for r in tabs[1]["data"])
        if fin:
            res["ratio"], res["fin"] = round(mv / fin * 100, 2), round(fin / 1e8, 1)
    return res


def cboe(iso):
    r = requests.get(f"https://cdn.cboe.com/data/us/options/market_statistics/daily/{iso}_daily_options", headers=UA, timeout=30)
    if r.status_code != 200:
        return None
    try:
        rs = {x["name"]: num(x["value"]) for x in r.json().get("ratios", [])}
    except ValueError:
        return None
    if not rs.get("TOTAL PUT/CALL RATIO"):
        return None
    return {"total": rs.get("TOTAL PUT/CALL RATIO"), "equity": rs.get("EQUITY PUT/CALL RATIO"),
            "index": rs.get("INDEX PUT/CALL RATIO"), "spx": rs.get("SPX + SPXW PUT/CALL RATIO")}


def taifex_range(start, end):
    """台指選 P/C（成交量、未平倉）與外資台指期淨未平倉；期交所單次查詢以一個月為限。"""
    fmt = lambda d: d.strftime("%Y/%m/%d")
    pc, txf = {}, {}
    cur = start
    while cur <= end:
        stop = min(cur + dt.timedelta(days=28), end)
        p = {"queryStartDate": fmt(cur), "queryEndDate": fmt(stop)}
        r = requests.get("https://www.taifex.com.tw/cht/3/pcRatioExcel", params=p, headers=UA, timeout=40)
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", r.text, re.S):
            c = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            if len(c) == 7 and re.match(r"\d{4}/\d+/\d+", c[0]):
                d = dt.datetime.strptime(c[0], "%Y/%m/%d").strftime("%Y-%m-%d")
                pc[d] = {"vol": num(c[3]), "oi": num(c[6])}
        # 結束日若是還沒有資料的日子（如當天早上），期交所整段都不回傳，所以逐日往前退
        for back in range(0, 6):
            q = {**p, "queryEndDate": fmt(stop - dt.timedelta(days=back)), "commodityId": "TXF"}
            if stop - dt.timedelta(days=back) < cur:
                break
            r = requests.get("https://www.taifex.com.tw/cht/3/futContractsDateDown", params=q, headers=UA, timeout=40)
            r.encoding = "big5"
            got = 0
            for row in csv.reader(io.StringIO(r.text)):
                if len(row) >= 14 and row[1].strip() == "臺股期貨" and "外資" in row[2]:
                    txf[dt.datetime.strptime(row[0].strip(), "%Y/%m/%d").strftime("%Y-%m-%d")] = num(row[13])
                    got += 1
            if got:
                break
            time.sleep(1)
        cur = stop + dt.timedelta(days=1)
        time.sleep(1)
    return pc, txf


def pc_events(store):
    """把 store 新抓到的 Cboe／期交所 P/C 併入長歷史，算各事件前後每天在前一年的百分位。"""
    import bisect
    hist = json.loads(PC_HIST.read_text(encoding="utf-8")) if PC_HIST.exists() else {"cboe": {}, "taifex": {}}
    for src, ks in (("cboe", ("total", "equity", "index")), ("taifex", ("vol", "oi"))):
        for d, v in store.get(src, {}).items():
            got = {k: v[k] for k in ks if v.get(k) is not None}
            if got:
                hist[src].setdefault(d, {}).update(got)
        hist[src] = dict(sorted(hist[src].items()))
    PC_HIST.write_text(json.dumps(hist, separators=(",", ":")), encoding="utf-8")
    out = {}
    for key, src, k in (("pc_total", "cboe", "total"), ("pc_equity", "cboe", "equity"), ("pc_index", "cboe", "index"),
                        ("pc_tw_oi", "taifex", "oi"), ("pc_tw_vol", "taifex", "vol")):
        ds = [d for d, v in hist[src].items() if v.get(k) is not None]
        vs = [hist[src][d][k] for d in ds]
        evs = []
        for i_ev, (name, date) in enumerate(PC_EVENTS):
            e = bisect.bisect_right(ds, date) - 1   # 事件日當天，休市則取前一個交易日
            if e < 0:
                continue
            pts = []
            for off in range(PC_WIN[0], PC_WIN[1] + 1):
                i = e + off
                if i < PC_LOOKBACK or i >= len(ds):
                    continue
                prev = vs[i - PC_LOOKBACK:i]
                pts.append([off, round(100 * sum(p <= vs[i] for p in prev) / len(prev)), vs[i], ds[i]])
            if pts:
                evs.append({"name": name, "date": ds[e], "current": i_ev == len(PC_EVENTS) - 1, "pts": pts})
        out[key] = evs
    return out


def update_store(backfill):
    store = json.loads(STORE.read_text(encoding="utf-8")) if STORE.exists() else {"cboe": {}, "twse": {}, "taifex": {}}
    today = dt.datetime.now(TW).date()
    days = [today - dt.timedelta(days=i) for i in range(backfill * 7 // 5 + 1)]
    days = sorted(d for d in days if d.weekday() < 5)

    try:  # Cboe：美東晚間才有當日檔，缺的日期每次重試
        n = 0
        for d in days:
            iso = d.isoformat()
            if iso not in store["cboe"]:
                v = cboe(iso)
                if v:
                    store["cboe"][iso] = v
                    n += 1
        note("Cboe", True, max(store["cboe"], default=None))
    except Exception as e:
        note("Cboe", False, max(store["cboe"], default=None), e)

    try:  # 證交所：法人下午、漲跌家數收盤後、融資晚間，各自缺才補
        for d in days:
            iso, ymd = d.isoformat(), d.strftime("%Y%m%d")
            rec = store["twse"].get(iso, {})
            if "fi" not in rec:
                v = twse_flows(ymd)
                if v:
                    rec.update(v)
            if rec and ("ratio" not in rec or "up" not in rec):
                rec.update(twse_breadth_margin(ymd))
            if rec:
                store["twse"][iso] = rec
        note("證交所", True, max((k for k, v in store["twse"].items() if "fi" in v), default=None))
    except Exception as e:
        note("證交所", False, max(store["twse"], default=None), e)

    try:
        pc, txf = taifex_range(days[0], days[-1])
        for k, v in pc.items():
            store["taifex"].setdefault(k, {}).update(v)
        for k, v in txf.items():
            store["taifex"].setdefault(k, {})["txf"] = v
        note("期交所", bool(pc and txf), max((k for k, v in store["taifex"].items() if "txf" in v), default=None), None if pc and txf else "P/C 或台指期未抓到")
    except Exception as e:
        note("期交所", False, max(store["taifex"], default=None), e)

    for k in store:   # 只留近 300 個日期
        store[k] = dict(sorted(store[k].items())[-300:])
    STORE.write_text(json.dumps(store, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return store


# ---------------------------------------------------------------- 計算
def index_position(rows, live):
    """高點＝PEAK_DATE 收盤（休市則取前一交易日）；前低＝該日之後最低收盤。盤中那筆只顯示，不進高低點計算。"""
    done = rows[:-1] if live else rows
    peak = [r for r in done if r[0] <= PEAK_DATE][-1]
    low = min((r for r in done if r[0] >= peak[0]), key=lambda x: x[1])
    last = rows[-1]
    prev = done[-1][1] if live else done[-2][1]
    pct = lambda a, b: round((a / b - 1) * 100, 2)
    res = {"last": last[1], "date": last[0], "live": live, "chg": pct(last[1], prev),
           "peak": peak, "low": low, "fromPeak": pct(last[1], peak[1]), "fromLow": pct(last[1], low[1])}
    span = peak[1] - low[1]
    res["retrace"] = round((last[1] - low[1]) / span * 100, 1) if span > 0 else None
    res["levels"] = [{"name": f"{r * 100:.1f}%".replace(".0%", "%"), "v": round(low[1] + span * r, 2)} for r in RETRACE] if span > 0 else []
    nxt = next((x for x in res["levels"] if x["v"] > last[1]), None)
    res["next"] = {**nxt, "dist": pct(nxt["v"], last[1])} if nxt else None
    # 近 10 個交易日最大單日跌幅（≥2%）的前一日收盤：回補大跌缺口的參考價
    drops = [(done[i][1] / done[i - 1][1] - 1, i) for i in range(max(1, len(done) - 10), len(done))]
    worst = min(drops, default=None)
    if worst and worst[0] <= -0.02:
        i = worst[1]
        res["gap"] = {"date": done[i][0], "drop": round(worst[0] * 100, 2), "v": done[i - 1][1]}
    return res


def row(key, label, group, series, unit="", digits=2, pol=0, method="chg5", flat=0.0, scale=None, tip=""):
    """方向：chg5＝最新對 5 筆前；ma5＝5 日均對 5 筆前的 5 日均；sum5＝近 5 日累計（看正負）。pol：1 上升為好轉、-1 上升為惡化、0 不判好壞。"""
    if not series:
        return {"key": key, "label": label, "group": group, "series": [], "empty": True, "tip": tip}
    vals = [v for _, v in series]
    out = {"key": key, "label": label, "group": group, "unit": unit, "digits": digits, "method": method, "tip": tip,
           "last": vals[-1], "date": series[-1][0], "series": [[d, round(v, 4)] for d, v in series[-60:]]}
    if method == "sum5":
        delta = sum(vals[-5:])
        out["measure"] = round(delta, digits)
        out["dir"] = ("好轉" if delta > 0 else "惡化") if pol else ("上升" if delta > 0 else "下降")
        return out
    if method == "ma5":
        a, b = sum(vals[-5:]) / len(vals[-5:]), sum(vals[-10:-5]) / max(1, len(vals[-10:-5]))
    else:
        a, b = vals[-1], vals[-6] if len(vals) > 5 else vals[0]
    delta = a - b
    out["measure"] = round(delta, digits + 1)
    if abs(delta) <= flat:
        out["dir"] = "持平"
    elif pol == 0:
        out["dir"] = "上升" if delta > 0 else "下降"
    else:
        out["dir"] = "好轉" if delta * pol > 0 else "惡化"
    return out


def main():
    backfill = int(sys.argv[sys.argv.index("--backfill") + 1]) if "--backfill" in sys.argv else 5
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    series, live, mtime = old.get("series", {}), old.get("live", {}), old.get("mtime", {})

    fails, latest = [], {}
    for key, sym, adj in [(k, s, k == "t0050") for k, _, s in INDICES + FUTURES + BOND_ETF] + [(k, s, False) for k, s in OTHER_YAHOO.items()]:
        try:
            series[key], live[key], mtime[key] = yahoo(sym, adj)
            series[key] = series[key][-KEEP:]
            latest[key] = series[key][-1][0]
        except Exception as e:
            fails.append(f"{sym}: {e}")
        time.sleep(0.15)
    note("Yahoo", not fails, max(latest.values(), default=None), "; ".join(fails) or None)

    try:
        for k, sid in FRED.items():
            series[k] = fred(sid)[-KEEP:]
        note("FRED 利差", True, series["oas_hy"][-1][0])
    except Exception as e:
        note("FRED 利差", False, (series.get("oas_hy") or [[None]])[-1][0], e)
    try:
        s2, s10 = treasury()
        series["ust2"], series["ust10"] = s2[-KEEP:], s10[-KEEP:]
        note("美國財政部", True, s10[-1][0])
    except Exception as e:
        note("美國財政部", False, (series.get("ust10") or [[None]])[-1][0], e)

    store = update_store(backfill)
    take = lambda src, k: [[d, v[k]] for d, v in sorted(store[src].items()) if v.get(k) is not None]
    tw = store["twse"]
    upshare = [[d, round(v["up"] / (v["up"] + v["down"]) * 100, 1)] for d, v in sorted(tw.items()) if v.get("up") is not None and v.get("down") is not None and v["up"] + v["down"]]

    S = lambda k: series.get(k) or []

    def ratio(a, b):
        den = dict(S(b))
        return [[d, v / den[d]] for d, v in S(a) if d in den]

    rows = [
        row("spy_rsp", "美股：市值加權對等權重（SPY÷RSP）", "廣度", ratio("spy", "rsp"), pol=1, digits=3, flat=0.002, tip="上升代表權值股走得比多數股票強"),
        row("up_share", "台股：上市股票上漲家數占比", "廣度", upshare, unit="%", digits=1, pol=1, method="ma5", flat=1, tip="上漲÷（上漲＋下跌），看 5 日均方向"),
        row("vix", "VIX", "波動率", S("vix"), pol=-1, flat=0.2, tip="持續回落代表恐慌消退"),
        row("vix_term", "VIX÷VIX3M", "波動率", ratio("vix", "vix3m"), pol=-1, digits=3, flat=0.005, tip="大於 1 為近月恐慌高於遠月（倒掛）"),
        row("pc_total", "美股總 Put/Call", "Put/Call", take("cboe", "total"), method="ma5", flat=0.01, tip="Cboe；看 5 日均方向，單日雜訊多"),
        row("pc_equity", "美股個股 Put/Call", "Put/Call", take("cboe", "equity"), method="ma5", flat=0.01, tip="較能反映散戶情緒"),
        row("pc_index", "美股指數 Put/Call", "Put/Call", take("cboe", "index"), method="ma5", flat=0.01, tip="較能反映法人避險"),
        row("pc_tw_oi", "台指選 Put/Call（未平倉）", "Put/Call", take("taifex", "oi"), unit="%", method="ma5", flat=1, tip="期交所買賣權未平倉比"),
        row("pc_tw_vol", "台指選 Put/Call（成交量）", "Put/Call", take("taifex", "vol"), unit="%", method="ma5", flat=1, tip="期交所買賣權成交量比"),
        row("ratio", "大盤融資維持率", "台股籌碼", take("twse", "ratio"), unit="%", pol=1, flat=0.5, tip="160% 以上為正常水位。<br>150%-160% 為中型修正。<br>150% 以下為股災級修正，2020年疫情，2022年升息約為 140%。"),
        row("fin", "融資餘額", "台股籌碼", take("twse", "fin"), unit=" 億", digits=0, flat=5, tip="下降代表去槓桿，好壞要配合維持率看"),
        row("fi", "外資買賣超（近 5 日累計）", "台股籌碼", take("twse", "fi"), unit=" 億", digits=0, pol=1, method="sum5", tip="最新欄為當日、變化欄為近 5 日累計"),
        row("it", "投信買賣超（近 5 日累計）", "台股籌碼", take("twse", "it"), unit=" 億", digits=0, pol=1, method="sum5", tip="最新欄為當日、變化欄為近 5 日累計"),
        row("de", "自營商買賣超（近 5 日累計）", "台股籌碼", take("twse", "de"), unit=" 億", digits=0, pol=1, method="sum5", tip="含自行買賣與避險"),
        row("txf", "外資台指期淨未平倉", "台股籌碼", take("taifex", "txf"), unit=" 口", digits=0, pol=1, flat=200, tip="負值為淨空單，回升代表空單減少"),
        row("oas_hy", "垃圾級利差", "信用利差", S("oas_hy"), unit=" bp", digits=0, pol=-1, flat=2, tip="ICE BofA，FRED 約晚一個工作日"),
        row("oas_ig", "投資級利差", "信用利差", S("oas_ig"), unit=" bp", digits=0, pol=-1, flat=1, tip="ICE BofA，FRED 約晚一個工作日"),
        row("ust10", "美國 10 年期殖利率", "公債殖利率", S("ust10"), unit="%", flat=0.01, tip="要和股市對照：殖利率跌、股也跌偏避險；殖利率跌、股漲對估值有利"),
        row("ust2", "美國 2 年期殖利率", "公債殖利率", S("ust2"), unit="%", flat=0.01, tip="反映政策利率預期"),
    ] + [row(k, n, "台灣債券 ETF", S(k), flat=0.02, tip="收盤價；此類 ETF 主要反映美債與匯率") for k, n, _ in BOND_ETF]

    # 隔夜傳導
    overnight = []
    for k, n, sym in FUTURES:
        s = S(k)
        try:
            path, last, last_t = intraday(sym)
        except Exception as e:
            print(f"期貨走勢 {sym} 失敗：{e}")
            path, last, last_t = [], s[-1][1] if s else None, mtime.get(k)
        base = path[0][1] if path else s[-2][1] if len(s) >= 2 else None   # 用走勢起點（前一次收盤）；Yahoo 日線有時缺當前這筆，不能靠倒數第二筆
        if last is not None and base:
            overnight.append({"key": k, "name": n, "last": last, "chg": round((last / base - 1) * 100, 2), "time": last_t, "digits": 2, "line": path, "base": base,
                              "extra": "成交稀少，請留意報價時間" if k == "soxf" else None})
    try:
        overnight.append(taifex_txf())
    except Exception as e:
        print(f"台指期失敗：{e}")
        overnight += [o for o in old.get("overnight", []) if o.get("key") == "txf_q"]   # 抓不到就沿用上次，報價時間會顯示舊值
    tsm, t2330, fx = S("tsm"), S("t2330"), S("usdtwd")
    if len(tsm) >= 2 and t2330 and fx:
        try:
            path, last, last_t = intraday("TSM", prepost=True, gap=0)
        except Exception as e:
            print(f"ADR 走勢失敗：{e}")
            path, last, last_t = [], None, None
        last, last_t = last or tsm[-1][1], last_t or mtime.get("tsm")
        base = tsm[-2][1] if live.get("tsm") else tsm[-1][1]     # 盤中對前一日收盤；盤前盤後對最近一次正常盤收盤
        overnight.append({"key": "tsm_q", "name": "台積電 ADR", "last": last, "chg": round((last / base - 1) * 100, 2), "time": last_t, "digits": 2, "line": path, "base": base,
                          "extra": f"{us_session(last_t)}；折合台幣 {last * fx[-1][1] / 5:,.0f} 元／股，對台股 {t2330[-1][1]:,.0f} 元溢價 {(last * fx[-1][1] / 5 / t2330[-1][1] - 1) * 100:+.1f}%"})

    indices = []
    for k, n, sym in INDICES:
        if S(k):
            indices.append({"key": k, "name": n, "sym": sym, "series": [[d, round(v, 2)] for d, v in S(k) if d >= CHART_START], **index_position(S(k), bool(live.get(k)))})

    try:
        pcev = pc_events(store)
    except Exception as e:
        pcev = old.get("pcEvents", {})
        print("ERR pc_events", e)
    now = dt.datetime.now(TW)
    OUT.write_text(json.dumps({"updated": now.strftime("%Y/%m/%d %H:%M"), "status": status, "indices": indices, "overnight": overnight,
                               "rows": rows, "series": series, "live": live, "mtime": mtime,
                               "pcEvents": pcev}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(now, {k: (v["ok"], v["asof"]) for k, v in status.items()})
    for k, v in status.items():
        if v["err"]:
            print("ERR", k, v["err"])


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
