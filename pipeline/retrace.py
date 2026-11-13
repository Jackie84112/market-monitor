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
from amd import daily, r2, RETRACE, TW  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STOCKS = [
    {"key": "mediatek", "sym": "2454.TW", "name": "聯發科", "en": "MediaTek", "code": "2454", "high": "2026-10-06", "low": "2026-11-06", "dec": 0, "ccy": "TWD"},
    {"key": "avgo", "sym": "AVGO", "name": "博通", "en": "Broadcom", "code": "AVGO", "high": "2026-10-06", "low": "2026-11-06", "dec": 2, "ccy": "USD"},
]


def build(s):
    rows, live, _ = daily(s["sym"])
    rows = [x for x in rows if not (x["v"] == 0 and x["h"] == x["l"])]   # 休市日的假資料（Yahoo 偶爾會補一筆）
    V = [x["v"] / 1e6 for x in rows]
    hi_row = next(x for x in rows if x["d"] == s["high"])
    lo_row = next(x for x in rows if x["d"] == s["low"])
    hi, lo = hi_row["h"], lo_row["l"]
    cur = rows[-1]["c"]
    li = rows.index(lo_row)
    swing = {"high": {"date": hi_row["d"], "v": r2(hi)}, "low": {"date": lo_row["d"], "v": r2(lo)},
             "drop": r2((lo / hi - 1) * 100, 1), "retrace": r2((cur - lo) / (hi - lo) * 100, 1),
             "lowVol": r2(V[li], 1), "lowChg": r2((lo_row["c"] / rows[li - 1]["c"] - 1) * 100),
             "path": [[x["d"], r2(x["c"]), r2(V[i], 1), r2((x["c"] / rows[i - 1]["c"] - 1) * 100)] for i, x in enumerate(rows) if x["d"] > s["low"]],
             "levels": [{"name": f"{p * 100:.1f}%", "v": r2(lo + p * (hi - lo)), "hit": cur >= lo + p * (hi - lo)} for p in RETRACE]}
    return {"updated": dt.datetime.now(TW).strftime("%Y/%m/%d %H:%M"), "name": s["name"], "en": s["en"], "code": s["code"],
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
