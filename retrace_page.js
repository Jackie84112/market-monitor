// 回補走勢子頁共用腳本（聯發科 mediatek.html、博通 avgo.html）；圖的畫法與 amd.html 的「回補走勢」完全一致。
const $ = id => document.getElementById(id);
const fmt = (v, d = 2) => v == null ? "—" : Number(v).toLocaleString("en-US", {minimumFractionDigits: d, maximumFractionDigits: d});
const short = d => d ? d.slice(5).replace("-", "/") : "—";
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
let D;

function renderPage() {
  const sw = D.swing;
  document.title = D.name + " 回補走勢";
  $("sub").textContent = `${D.name}（${D.code}）${D.en}　｜　資料日：${D.asof.replace(/-/g, "/")}　｜　資料更新：${D.updated}（台灣時間）`;
  $("st").innerHTML = Object.entries(D.status).map(([k, s]) =>
    `<span class="chip ${s.ok ? "" : "r"}" title="${s.err ? esc(s.err) : ""}">${k} ${s.ok ? "至" : "抓取失敗，沿用至"} ${short(s.asof)}</span>`).join("");
  $("hsub").textContent = `${short(sw.high.date)} 高點至 ${short(sw.low.date)} 低點；以低點為原點，之後每日收盤；滑鼠移到點上，顯示該日的回補水位`;
  drawRetrace();
}

function initPage(key) {
  fetch("data/" + key + ".json", {cache: "no-store"}).then(r => r.json()).then(d => {
    D = d; renderPage();
    let t; addEventListener("resize", () => { clearTimeout(t); t = setTimeout(drawRetrace, 150); });
  }).catch(e => { $("sub").innerHTML = `<span style="color:#C02323">資料讀取失敗：${e}</span>`; console.error(e); });
}
