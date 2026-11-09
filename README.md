# 大盤監控

每日追蹤 S&P 500、Nasdaq-100、SOX、道瓊、0050、KOSPI 的反彈力道與位置。

- 網頁：`index.html`，讀 `data/monitor.json`、`data/manual.json`
- 資料：`python pipeline/build.py`（首次用 `--backfill 70` 回補）；GitHub Actions 平日每小時更新
- 手動：`data/manual.json` 的 P/E，FactSet 每週五出新版

方向欄只描述近 5 個交易日的變化，不是買賣訊號。
