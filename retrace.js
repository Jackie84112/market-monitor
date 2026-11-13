// 回補走勢子頁共用腳本（聯發科 mediatek.html、博通 avgo.html）；圖的畫法與 amd.html 的「回補走勢」完全一致。
const $ = id => document.getElementById(id);
const fmt = (v, d = 2) => v == null ? "—" : Number(v).toLocaleString("en-US", {minimumFractionDigits: d, maximumFractionDigits: d});
const short = d => d ? d.slice(5).replace("-", "/") : "—";
const esc = s => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
let D;

// 回補走勢：原點＝低點日最低價，Y 軸涵蓋 0%（低點）到 100%（高點）；滑鼠移到點上自動標出該日回補水位（虛線）與只有股價的浮標；下方為每日量柱
function drawRetrace() {
  const el = $("rchart"), sw = D.swing, lo = sw.low.v, hi = sw.high.v, span = hi - lo;
  const path0 = sw.path || [];
  const pts = [[sw.low.date, lo], ...path0.map(p => [p[0], p[1]])], n = pts.length;
  const vols = sw.lowVol != null && path0.every(p => p[2] != null) ? [sw.lowVol, ...path0.map(p => p[2])] : null;
  const chgs = [sw.lowChg, ...path0.map(p => p[3])];
  const W = Math.max(el.clientWidth, 280), narrow = W < 560;
  const L = 54, R = narrow ? 94 : 132, T = 16, PH = narrow ? 270 : 340, DH = 34, VG = 8, VH = vols ? (narrow ? 78 : 92) : 0;
  const mac = sw.macd && sw.macd.length === n ? sw.macd : null, MG = 16, MH = mac ? (narrow ? 170 : 230) : 0;
  const VT = T + PH + DH + VG, MT = VT + (vols ? VH : 0) + MG, H = (mac ? MT + MH : vols ? VT + VH : T + PH + DH) + 8, bottom = T + PH;
  const slots = Math.max(n, 8), pw = (W - L - R) / (slots - 1);
  const X = i => L + pw * i, Y = v => T + PH * (1 - (v - lo) / span), pc = v => (v - lo) / span * 100;
  const vmax = vols ? Math.max(...vols) : 1, vbase = VT + VH, vbh = VH - 16, vbw = Math.min(pw * .5, 36), barH = v => Math.max(1, vbh * v / vmax);
  const fixed = sw.levels.slice(0, 3);
  const ACC = "#B04A2F", dec = D.dec;
  const gstep = [10, 20, 25, 50, 100, 200, 250, 500, 1000].find(s => span / s <= 6) || 1000;
  let g = "";
  for (let p = Math.ceil(lo / gstep) * gstep; p < hi; p += gstep) {
    if (Y(lo) - Y(p) < 16 || Y(p) - Y(hi) < 16) continue;   // 離高低點標籤太近就略過，避免文字重疊
    g += `<line x1="${L}" x2="${W - R}" y1="${Y(p)}" y2="${Y(p)}" stroke="#EEEDE8" stroke-width="1"/><text x="${L - 6}" y="${Y(p) + 3.5}" font-size="10.5" fill="#9AA0A6" text-anchor="end">${p}</text>`;
  }
  // 0% / 100% 邊界與座標軸
  g += `<line x1="${L}" x2="${W - R}" y1="${Y(hi)}" y2="${Y(hi)}" stroke="#B9BDC2" stroke-width="1"/>
    <line x1="${L}" x2="${L}" y1="${T}" y2="${bottom}" stroke="#8C9096" stroke-width="1"/>
    <line x1="${L}" x2="${W - R}" y1="${bottom}" y2="${bottom}" stroke="#8C9096" stroke-width="1"/>
    <text x="${L - 6}" y="${Y(hi) + 3.5}" font-size="10.5" fill="#22262B" font-weight="600" text-anchor="end">${fmt(hi, dec)}</text>
    <text x="${L - 6}" y="${bottom + 3.5}" font-size="10.5" fill="#22262B" font-weight="600" text-anchor="end">${fmt(lo, dec)}</text>
    <text x="${W - R + 6}" y="${Y(hi) + 3.5}" font-size="10.5" fill="#22262B" font-weight="600">100%　${fmt(hi, dec)}</text>
    <text x="${W - R + 6}" y="${bottom + 3.5}" font-size="10.5" fill="#22262B" font-weight="600">0%　${fmt(lo, dec)}</text>`;
  fixed.forEach(l => {
    g += `<line x1="${L}" x2="${W - R}" y1="${Y(l.v)}" y2="${Y(l.v)}" stroke="#6B7178" stroke-width="1.2" stroke-dasharray="6 4"/>
      <text x="${W - R + 6}" y="${Y(l.v) + 3.5}" font-size="10.5" fill="#4B5158">${l.name}　${fmt(l.v, dec)}</text>`;
  });
  // X 軸：每個交易日一格，標籤太擠就隔幾格標一次
  const step = Math.max(1, Math.ceil(46 / pw));
  pts.forEach((p, i) => {
    g += `<line x1="${X(i)}" x2="${X(i)}" y1="${bottom}" y2="${bottom + 4}" stroke="#8C9096"/>`;
    if (i % step === 0 || i === n - 1) g += `<text x="${X(i)}" y="${bottom + 17}" font-size="10.5" fill="#6B7178" text-anchor="middle">${short(p[0])}</text>`;
  });
  g += `<text x="${(L + W - R) / 2}" y="${bottom + 31}" font-size="10.5" fill="#9AA0A6" text-anchor="middle">交易日</text>`;
  // 折線與點
  const path = pts.map((p, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(p[1]).toFixed(1)).join("");
  g += `<path d="${path}" fill="none" stroke="var(--chart)" stroke-width="2.2" stroke-linejoin="round"/>`;
  pts.forEach((p, i) => {
    g += i === 0
      ? `<circle cx="${X(0)}" cy="${Y(p[1])}" r="5" fill="#fff" stroke="var(--chart)" stroke-width="2"/>`
      : `<circle cx="${X(i)}" cy="${Y(p[1])}" r="${i === n - 1 ? 5.5 : 4}" fill="var(--chart)" stroke="#fff" stroke-width="1.5"/>`;
  });
  g += `<text x="${X(0) + 9}" y="${Y(lo) - 9}" font-size="11" fill="#22262B">原點：${short(sw.low.date)} 最低 ${fmt(lo, dec)}</text>`;
  // 每日量柱（紅漲綠跌），與上方的點對齊
  if (vols) {
    g += `<line x1="${L}" x2="${W - R}" y1="${vbase}" y2="${vbase}" stroke="#8C9096" stroke-width="1"/>
      <text x="${W - R}" y="${VT + 8}" font-size="10" fill="#9AA0A6" text-anchor="end">成交量（百萬股）</text>`;
    vols.forEach((v, i) => {
      const h = barH(v);
      g += `<rect x="${(X(i) - vbw / 2).toFixed(1)}" y="${(vbase - h).toFixed(1)}" width="${vbw.toFixed(1)}" height="${h.toFixed(1)}" rx="1.5" fill="${chgs[i] >= 0 ? "var(--up)" : "var(--dn)"}" opacity=".55"/>
        <text x="${X(i)}" y="${vbase - h - 4}" font-size="10.5" fill="#4B5158" text-anchor="middle">${fmt(v, 1)}</text>`;
    });
  }
  // MACD（12,26,9）：柱狀圖＝柱（紅正綠負）、MACD 線（藍）、信號線（橘），與上方的點對齊
  if (mac) {
    // 縱軸只涵蓋實際數值（含 0），不再對稱於 0，區間才會拉得開；柱、線共用同一把尺
    const all = mac.flatMap(m => [m[1], m[2], m[3]]).concat(0), mn = Math.min(...all), mx = Math.max(...all), pad = (mx - mn) * .14 || 1;
    const mTop = MT + 18, mBot = MT + MH - 4, lo2 = mn - pad, hi2 = mx + pad;
    const MY = v => mBot - (v - lo2) / (hi2 - lo2) * (mBot - mTop), mid = MY(0), mp = k => mac.map((m, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + MY(m[k]).toFixed(1)).join("");
    g += `<text x="${W - R}" y="${MT + 8}" font-size="10" fill="#9AA0A6" text-anchor="end">MACD（12, 26, 9）</text>
      <line x1="${L}" x2="${L}" y1="${mTop}" y2="${mBot}" stroke="#8C9096" stroke-width="1"/>
      <line x1="${L}" x2="${W - R}" y1="${mid}" y2="${mid}" stroke="#8C9096" stroke-width="1"/>
      <text x="${W - R + 6}" y="${mid + 3.5}" font-size="10.5" fill="#9AA0A6">0</text>
      <text x="${L - 6}" y="${MY(mx) + 3.5}" font-size="10.5" fill="#9AA0A6" text-anchor="end">${fmt(mx, dec)}</text>
      <text x="${L - 6}" y="${MY(mn) + 3.5}" font-size="10.5" fill="#9AA0A6" text-anchor="end">${fmt(mn, dec)}</text>`;
    mac.forEach((m, i) => {
      const y = MY(m[3]), h = Math.max(1, Math.abs(y - mid)), up = m[3] >= 0;
      g += `<rect x="${(X(i) - vbw / 2).toFixed(1)}" y="${(up ? y : mid).toFixed(1)}" width="${vbw.toFixed(1)}" height="${h.toFixed(1)}" rx="1.5" fill="${up ? "var(--up)" : "var(--dn)"}" opacity=".5"/>
        <text x="${X(i)}" y="${up ? y - 4 : y + h + 11}" font-size="10" fill="#4B5158" text-anchor="middle">${fmt(m[3], dec)}</text>`;
    });
    g += `<path d="${mp(1)}" fill="none" stroke="var(--chart)" stroke-width="2.2" stroke-linejoin="round"/><path d="${mp(2)}" fill="none" stroke="#F59E0B" stroke-width="2.2" stroke-linejoin="round"/>`;
    mac.forEach((m, i) => { g += `<circle cx="${X(i)}" cy="${MY(m[1])}" r="3.5" fill="var(--chart)" stroke="#fff" stroke-width="1.2"/><circle cx="${X(i)}" cy="${MY(m[2])}" r="3.5" fill="#F59E0B" stroke="#fff" stroke-width="1.2"/>`; });
    // 交叉：柱子由負轉正＝黃金交叉、由正轉負＝死亡交叉（MACD 線穿越信號線），標在轉折那天
    mac.forEach((m, i) => {
      if (!i || (m[3] >= 0) === (mac[i - 1][3] >= 0)) return;
      const gold = m[3] >= 0, cx = (X(i) + X(i - 1)) / 2, ratio = Math.abs(mac[i - 1][3]) / (Math.abs(mac[i - 1][3]) + Math.abs(m[3])), cy = MY(mac[i - 1][1] + (m[1] - mac[i - 1][1]) * ratio);
      const px = X(i - 1) + (X(i) - X(i - 1)) * ratio, col = gold ? "var(--up)" : "var(--dn)";
      g += `<circle cx="${px}" cy="${cy}" r="8" fill="none" stroke="${col}" stroke-width="2"/>
        <text x="${px}" y="${cy - 13}" font-size="11.5" font-weight="700" fill="${col}" text-anchor="middle" style="paint-order:stroke;stroke:#fff;stroke-width:3px">${gold ? "黃金交叉" : "死亡交叉"}</text>`;
    });
    const last = mac[n - 1], yl = MY(last[1]), ys = MY(last[2]);
    g += `<text x="${W - R + 6}" y="${yl + (Math.abs(yl - ys) < 13 ? (last[1] > last[2] ? -4 : 12) : 3.5)}" font-size="10.5" fill="var(--chart)">MACD　${fmt(last[1], dec)}</text><text x="${W - R + 6}" y="${ys + (Math.abs(yl - ys) < 13 ? (last[1] > last[2] ? 12 : -4) : 3.5)}" font-size="10.5" fill="#D97706">信號　${fmt(last[2], dec)}</text>`;
  }
  el.innerHTML = `<svg width="${W}" height="${H}" role="img" aria-label="${D.en} 回補走勢圖與每日成交量">${g}<g id="rhov"></g><rect x="0" y="0" width="${W}" height="${H}" fill="transparent"/></svg>`;
  const svg = el.firstChild, hov = svg.querySelector("#rhov");
  // 滑鼠移到點上：該日回補水位的虛線＋浮標（浮標只有股價）；同一天的量柱加外框
  const show = i => {
    const v = pts[i][1], x = X(i), y = Y(v), txt = fmt(v, dec), w = txt.length * 7.6 + 18, h = 24;
    const bx = Math.max(L + 2, Math.min(W - R - w - 2, x - w / 2)), by = y - 16 - h >= T ? y - 16 - h : y + 16;
    const vb = vols ? `<rect x="${(X(i) - vbw / 2).toFixed(1)}" y="${(vbase - barH(vols[i])).toFixed(1)}" width="${vbw.toFixed(1)}" height="${barH(vols[i]).toFixed(1)}" rx="1.5" fill="none" stroke="${ACC}" stroke-width="1.6"/>` : "";
    hov.innerHTML = `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" stroke="${ACC}" stroke-width="1.5" stroke-dasharray="3 3"/>
      <circle cx="${x}" cy="${y}" r="7" fill="none" stroke="${ACC}" stroke-width="2"/>
      <text x="${W - R - 6}" y="${y - 7}" font-size="11.5" font-weight="600" fill="${ACC}" text-anchor="end" style="paint-order:stroke;stroke:#fff;stroke-width:3px">${x + 14 < W - R - 6 - 66 ? "回補 " : ""}${fmt(pc(v), 1)}%</text>
      <g><rect x="${bx}" y="${by}" width="${w}" height="${h}" rx="6" fill="#22262B"/><text x="${bx + w / 2}" y="${by + 16.5}" font-size="13" font-weight="600" fill="#fff" text-anchor="middle">${txt}</text></g>${vb}`;
  };
  const near = e => {
    const r = svg.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top, i = Math.round((x - L) / pw);
    return i >= 0 && i <= n - 1 && Math.hypot(x - X(i), y - Y(pts[i][1])) <= 18 ? i : -1;
  };
  svg.addEventListener("pointermove", e => {
    const i = near(e);
    svg.style.cursor = i >= 0 ? "pointer" : "default";
    if (i >= 0) show(i); else hov.innerHTML = "";
  });
  svg.addEventListener("pointerdown", e => { const i = near(e); if (i >= 0) show(i); else hov.innerHTML = ""; });   // 觸控螢幕：點一下顯示
  svg.addEventListener("pointerleave", e => { if (e.pointerType !== "touch") hov.innerHTML = ""; });
  $("rlegend").innerHTML = `<span><i style="background:var(--chart)"></i>每日收盤</span><span><i style="background:#6B7178;height:0;border-top:2px dashed #6B7178"></i>固定回補位（38.2% / 50% / 61.8%）</span><span><i style="background:${ACC};height:0;border-top:2px dashed ${ACC}"></i>滑鼠所在點的回補位</span>${vols ? "<span>量柱：紅漲綠跌</span>" : ""}${mac ? '<span><i style="background:#F59E0B"></i>MACD 信號線</span><span><i style="background:var(--chart)"></i>MACD 線</span><span>MACD 柱：紅正綠負</span>' : ""}`;
}

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
