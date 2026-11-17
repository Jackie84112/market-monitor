// 回補走勢圖（聯發科、博通、AMD、各指數共用）：drawRetrace(容器, 資料, 圖例)；資料格式見 pipeline/retrace.py 的 swing
// 需要頁面先有 $、fmt、short 三個小工具
// 回補走勢：原點＝低點日最低價，Y 軸涵蓋 0%（低點）到 100%（高點）；滑鼠移到點上自動標出該日回補水位（虛線）與只有股價的浮標；下方為每日量柱
function drawRetrace(el = $("rchart"), data = null, leg = $("rlegend")) {
  const DD = data || D, sw = DD.swing, lo = sw.low.v, hi = sw.high.v, span = hi - lo;
  // 時間範圍：預設「回補段」（低點起，現在的畫面）；若資料有 sw.hist（長日線歷史），可選 1 個月／3 個月／6 個月／2026（當年 1/1 起），
  // 成交量與 MACD 跟著同一個時間窗；再點一次已選的按鈕＝取消，回到預設畫面
  const wst = (drawRetrace.win = drawRetrace.win || {})[el.id] = (drawRetrace.win[el.id] || {mode: "swing"});
  const hist = sw.hist && wst.mode !== "swing" ? sw.hist : null;
  let pts, vols, chgs, hmac = null;
  if (hist) {
    const nDay = {"1m": 21, "3m": 63, "6m": 126}[wst.mode], y0 = hist[hist.length - 1][0].slice(0, 4) + "-01-01";
    const N = nDay ? Math.min(nDay, hist.length) : hist.length - Math.max(0, hist.findIndex(h => h[0] >= y0)), sl = hist.slice(hist.length - N);
    pts = sl.map(h => [h[0], h[1]]); vols = sl.map(h => h[2]); chgs = sl.map(h => h[3]); hmac = sl.map(h => [h[0], h[4], h[5], h[6]]);
  } else {
    const path0 = sw.path || [];
    pts = [[sw.low.date, lo], ...path0.map(p => [p[0], p[1]])];
    vols = sw.lowVol != null && path0.every(p => p[2] != null) ? [sw.lowVol, ...path0.map(p => p[2])] : null;
    chgs = [sw.lowChg, ...path0.map(p => p[3])];
  }
  const n = pts.length, dense = n > 40, oi = pts.findIndex(p => p[0] === sw.low.date);
  const W = Math.max(el.clientWidth, 280), narrow = W < 560;
  const st = (drawRetrace.st = drawRetrace.st || {})[el.id] = (drawRetrace.st || {})[el.id] || {vol: true, mac: true};   // 各面板展開狀態，重畫時保留
  const wideSc = !narrow && (DD.scen || []).some(s => s.text && s.text.length);   // 情境有說明文字時，右邊留一欄放「區間＋說明」
  const L = 54, R = narrow ? 94 : wideSc ? 268 : 132, T = 16, PH = narrow ? 270 : 340, DH = 34, VG = 10, TB = 28;
  const mac = hist ? hmac : (sw.macd && sw.macd.length === n ? sw.macd : null);
  const VH = vols && st.vol ? (narrow ? 78 : 92) : 0, MH = mac && st.mac ? (narrow ? 170 : 230) : 0;
  const VT = T + PH + DH + VG, VB = VT + TB, MT = VT + (vols ? TB + VH + VG : 0), MB = MT + TB;
  const H = (mac ? MB + MH : vols ? VB + VH : T + PH + DH) + 8, bottom = T + PH, bands = [];
  // 可收合的面板標題列：整條可點，▾ 展開／▸ 收起
  const bar = (y, key, label, open) => { bands.push([y, y + TB, key]);
    return `<rect x="0" y="${y}" width="${W}" height="${TB}" rx="6" fill="#EFEDE7"/><text x="12" y="${y + 19}" font-size="14" font-weight="700" fill="#22262B" style="cursor:pointer">${open ? "▾" : "▸"}　${label}</text>
      <text x="${W - 12}" y="${y + 18}" font-size="11" fill="#6B7178" text-anchor="end">${open ? "點此收起" : "點此展開"}</text>`; };
  // 均線（台股 20／60／120／240 日；美股 20／50／100／200 日，依 MA_SET 判斷）：用 sw.hist 長日線算，回補段與各時間範圍都畫；開關存 drawRetrace.ma[el.id]（Set），預設全關；頁面要放 MA_SEG
  const maSel = (drawRetrace.ma && drawRetrace.ma[el.id]) || new Set();
  const mas = sw.hist ? MA_SET(DD.code).filter(m => maSel.has(m.k)).map(m => {
    const H_ = sw.hist, idx = {}; let s = 0;
    H_.forEach((h, k) => { s += h[1]; if (k >= m.n) s -= H_[k - m.n][1]; if (k >= m.n - 1) idx[h[0]] = s / m.n; });
    return {...m, pts: pts.map(p => idx[p[0]] ?? null)};
  }) : [];
  const maV = mas.flatMap(m => m.pts.filter(v => v != null));
  // 情境模擬（選用）：DD.scen = [{color, tag, label, band:[下,上], pts:[[日期, 價], ...]}]；X 軸往右延伸到情境最後一天，只畫落在圖窗內的點
  const lastD = pts[n - 1][0], firstD = pts[0][0];
  const scen = (DD.scen || []).map(s => ({...s, pts: s.pts.filter(p => p[0] >= firstD)})).filter(s => s.pts.length > 1);
  const ext = [...new Set(scen.flatMap(s => s.pts.map(p => p[0])).filter(d => d > lastD))].sort();
  const dIx = Object.fromEntries([...pts.map(p => p[0]), ...ext].map((d, i) => [d, i]));
  const scV = scen.flatMap(s => [...s.pts.map(p => p[1]), ...(s.band || [])]);
  const slots = Math.max(n + ext.length, 8), pw = (W - L - R) / (slots - 1);
  const vtop = Math.max(hi, ...pts.map(p => p[1]), ...maV, ...scV), vbot = Math.min(lo, ...pts.map(p => p[1]), ...maV, ...scV), X = i => L + pw * i, Y = v => T + PH * (1 - (v - vbot) / (vtop - vbot)), pc = v => (v - lo) / span * 100;
  const vmax = vols ? Math.max(...vols) : 1, vbase = VB + VH, vbh = VH - 16, vbw = Math.min(pw * .5, 36), barH = v => Math.max(1, vbh * v / vmax);
  const fixed = sw.levels.slice(0, 3);
  const ACC = "#B04A2F", dec = DD.dec;
  const gstep = [10, 20, 25, 50, 100, 200, 250, 500, 1000].find(s => (vtop - vbot) / s <= 6) || 1000;
  let g = "";
  for (let p = Math.ceil(vbot / gstep) * gstep; p < vtop; p += gstep) {
    if (Math.abs(Y(lo) - Y(p)) < 16 || Math.abs(Y(p) - Y(hi)) < 16) continue;   // 離高低點標籤太近就略過，避免文字重疊
    g += `<line x1="${L}" x2="${W - R}" y1="${Y(p)}" y2="${Y(p)}" stroke="#EEEDE8" stroke-width="1"/><text x="${L - 6}" y="${Y(p) + 3.5}" font-size="10.5" fill="#9AA0A6" text-anchor="end">${p}</text>`;
  }
  // 0% / 100% 邊界與座標軸
  g += `<line x1="${L}" x2="${W - R}" y1="${Y(hi)}" y2="${Y(hi)}" stroke="#B9BDC2" stroke-width="1"/>
    <line x1="${L}" x2="${L}" y1="${T}" y2="${bottom}" stroke="#8C9096" stroke-width="1"/>
    <line x1="${L}" x2="${W - R}" y1="${bottom}" y2="${bottom}" stroke="#8C9096" stroke-width="1"/>
    <text x="${L - 6}" y="${Y(hi) + 3.5}" font-size="10.5" fill="#22262B" font-weight="600" text-anchor="end">${fmt(hi, dec)}</text>
    <line x1="${L}" x2="${W - R}" y1="${Y(lo)}" y2="${Y(lo)}" stroke="#B9BDC2" stroke-width="1"/><text x="${L - 6}" y="${Y(lo) + 3.5}" font-size="10.5" fill="#22262B" font-weight="600" text-anchor="end">${fmt(lo, dec)}</text>
    <text x="${W - R + 6}" y="${Y(hi) + 3.5}" font-size="10.5" fill="#22262B" font-weight="600">100%　${fmt(hi, dec)}</text>
    <text x="${W - R + 6}" y="${Y(lo) + 3.5}" font-size="10.5" fill="#22262B" font-weight="600">0%　${fmt(lo, dec)}</text>`;
  fixed.forEach(l => {
    g += `<line x1="${L}" x2="${W - R}" y1="${Y(l.v)}" y2="${Y(l.v)}" stroke="#6B7178" stroke-width="1.2" stroke-dasharray="6 4"/>
      <text x="${W - R + 6}" y="${Y(l.v) + 3.5}" font-size="10.5" fill="#4B5158">${l.name}　${fmt(l.v, dec)}</text>`;
  });
  // VPVR（成交量分布）：從左軸向右長的橫條；由「VPVR 範圍」開關選 10/6 起（15 分 K）或 2026 整年（日線）或關。
  // 滑鼠移到橫條上，左軸顯示該格股價、右側顯示回補水位（虛線）。資料見 pipeline/retrace.py、amd.py 的 vpvr / vpvr_daily
  const vm_ = (drawRetrace.vpm = drawRetrace.vpm || {})[el.id] || (typeof VPM === "undefined" ? "swing" : VPM);
  const vp0 = vm_ === "off" ? null : vm_ === "year" ? sw.vpYear : sw.vp, vp = vp0 && {...vp0, bins: vp0.bins.filter(b => b[1] > vbot && b[0] < vtop)}, vmx = vp ? Math.max(1e-9, ...vp.bins.map(b => b[2])) : 1, vpMaxW = (W - L - R) * .3, vpW = b => vpMaxW * b[2] / vmx;
  if (vp) vp.bins.forEach(b => {
    const y1 = Y(b[1]), y0 = Y(b[0]);
    g += `<rect x="${L}" y="${(y1 + .5).toFixed(1)}" width="${vpW(b).toFixed(1)}" height="${Math.max(1, y0 - y1 - 1).toFixed(1)}" fill="var(--chart)" opacity=".28"/>`;
  });
  // X 軸：每個交易日一格，標籤太擠就隔幾格標一次
  const step = Math.max(1, Math.ceil(46 / pw));
  pts.forEach((p, i) => {
    const lab = i % step === 0 || i === n - 1;
    if (!dense || lab) g += `<line x1="${X(i)}" x2="${X(i)}" y1="${bottom}" y2="${bottom + 4}" stroke="#8C9096"/>`;
    if (lab && (i === n - 1 || X(n - 1) - X(i) >= 40)) g += `<text x="${X(i)}" y="${bottom + 17}" font-size="10.5" fill="#6B7178" text-anchor="middle">${short(p[0])}</text>`;
  });
  ext.forEach((d, k) => {   // 情境延伸的日期：淡灰刻度
    const i = n + k, lab = i % step === 0 || k === ext.length - 1;
    if (lab && (k === ext.length - 1 || X(n + ext.length - 1) - X(i) >= 40) && X(i) - X(n - 1) >= 36) g += `<text x="${X(i)}" y="${bottom + 17}" font-size="10.5" fill="#B0B5BA" text-anchor="middle">${short(d)}</text>`;
  });
  g += `<text x="${(L + W - R) / 2}" y="${bottom + 31}" font-size="10.5" fill="#9AA0A6" text-anchor="middle">交易日</text>`;
  // 情境模擬：未來區段淡底、中性區間色帶、虛線路徑＋終點標籤（畫在收盤線下面）
  if (scen.length) {
    if (ext.length) g += `<rect x="${X(n - 1)}" y="${T}" width="${X(n + ext.length - 1) - X(n - 1)}" height="${PH}" fill="#E9E7E0" opacity=".45"/><text x="${X(n - 1) + 6}" y="${T + 12}" font-size="10.5" fill="#9AA0A6">情境模擬（示意）</text>`;
    scen.forEach(s => {
      const xs = s.pts.map(p => X(dIx[p[0]])), x0 = xs[0], x1 = xs[xs.length - 1];
      if (s.band) g += `<rect x="${x0}" y="${Y(s.band[1])}" width="${x1 - x0}" height="${Y(s.band[0]) - Y(s.band[1])}" fill="${s.color}" opacity=".1"/>`;
    });
    const taken = [Y(hi), Y(lo), ...fixed.map(l => Y(l.v))];   // 右側已有的回補位標籤，終點標籤避開（窄版）
    const blocks = [];   // 寬版：回補位標籤右邊再開一欄，放區間名稱＋說明（同下方後續走勢情境圖的文字），由上到下排開不重疊
    scen.forEach(s => {
      const d = s.pts.map((p, k) => (k ? "L" : "M") + X(dIx[p[0]]).toFixed(1) + " " + Y(p[1]).toFixed(1)).join(""), e = s.pts[s.pts.length - 1], ex = X(dIx[e[0]]), ey = Y(e[1]);
      g += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2.2" stroke-dasharray="7 5"/><circle cx="${ex}" cy="${ey}" r="3.5" fill="${s.color}"/>`;
      if (wideSc) { blocks.push({s, ex, ey, lines: s.text || []}); return; }
      let ty = ey;
      for (let k = 0; k < 6; k++) { const c = taken.find(t => Math.abs(t - ty) < 13); if (c == null) break; ty = c + (ty >= c ? 13 : -13); }
      taken.push(ty);
      g += `<text x="${ex + 6}" y="${ty + 4}" font-size="11" font-weight="700" fill="${s.color}" style="paint-order:stroke;stroke:#fff;stroke-width:3px">${s.tag}</text>`;
    });
    if (blocks.length) {
      const bx = W - R + 104, LH = 16;
      blocks.sort((a, b) => a.ey - b.ey);
      let floor = T;
      blocks.forEach(b => {
        const h = LH * (1 + b.lines.length);
        b.top = Math.max(floor, Math.min(b.ey - h / 2, T + PH - h)); floor = b.top + h + 8;
      });
      blocks.forEach(b => {
        const cy = b.top + 11;
        g += `<path d="M${b.ex} ${b.ey}L${W - R + 96} ${b.ey}L${bx - 4} ${cy - 4}" fill="none" stroke="${b.s.color}" stroke-width="1" opacity=".7"/>
          <rect x="${bx}" y="${b.top}" width="58" height="19" rx="5" fill="${b.s.color}"/><text x="${bx + 29}" y="${b.top + 13.5}" font-size="11.5" font-weight="700" fill="#fff" text-anchor="middle">${b.s.tag}</text>`
          + b.lines.map((t, k) => `<text x="${bx}" y="${b.top + 19 + LH * (k + 1) - 2}" font-size="12.5" font-weight="600" fill="#22262B">${t}</text>`).join("");
      });
    }
  }
  // 折線與點
  mas.forEach(m => {   // 均線畫在收盤線下面
    let d = "", pen = false;
    m.pts.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? "L" : "M") + X(i).toFixed(1) + " " + Y(v).toFixed(1); pen = true; });
    g += `<path d="${d}" fill="none" stroke="${m.c}" stroke-width="2" stroke-linejoin="round"/>`;
  });
  const path = pts.map((p, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(p[1]).toFixed(1)).join("");
  g += `<path d="${path}" fill="none" stroke="var(--chart)" stroke-width="2.2" stroke-linejoin="round"/>`;
  pts.forEach((p, i) => {
    if (dense && i !== n - 1 && i !== oi) return;
    g += i === oi
      ? `<circle cx="${X(i)}" cy="${Y(p[1])}" r="5" fill="#fff" stroke="var(--chart)" stroke-width="2"/>`
      : `<circle cx="${X(i)}" cy="${Y(p[1])}" r="${i === n - 1 ? 5.5 : 4}" fill="var(--chart)" stroke="#fff" stroke-width="1.5"/>`;
  });
  if (oi >= 0) g += `<text x="${X(oi) + (X(oi) > W - R - 150 ? -9 : 9)}" y="${Y(lo) - 9}" font-size="11" fill="#22262B" text-anchor="${X(oi) > W - R - 150 ? "end" : "start"}">原點：${short(sw.low.date)} ${DD.lowWord || "最低"} ${fmt(lo, dec)}</text>`;
  // 每日量柱（紅漲綠跌），與上方的點對齊
  if (vols) {
    g += bar(VT, "vol", "成交量（百萬股）", st.vol);
    if (st.vol) g += `<line x1="${L}" x2="${W - R}" y1="${vbase}" y2="${vbase}" stroke="#8C9096" stroke-width="1"/>`;
    if (st.vol) vols.forEach((v, i) => {
      const h = barH(v);
      g += `<rect x="${(X(i) - vbw / 2).toFixed(1)}" y="${(vbase - h).toFixed(1)}" width="${vbw.toFixed(1)}" height="${h.toFixed(1)}" rx="1.5" fill="${chgs[i] >= 0 ? "var(--up)" : "var(--dn)"}" opacity=".55"/>
        ${dense ? "" : `<text x="${X(i)}" y="${vbase - h - 4}" font-size="10.5" fill="#4B5158" text-anchor="middle">${fmt(v, 1)}</text>`}`;
    });
  }
  // MACD（12,26,9）：柱狀圖＝柱（紅正綠負）、MACD 線（藍）、信號線（橘），與上方的點對齊
  if (mac) g += bar(MT, "mac", "MACD（12, 26, 9）", st.mac);
  if (mac && st.mac) {
    // 縱軸只涵蓋實際數值（含 0），不再對稱於 0，區間才會拉得開；柱、線共用同一把尺
    const all = mac.flatMap(m => [m[1], m[2], m[3]]).concat(0), mn = Math.min(...all), mx = Math.max(...all), pad = (mx - mn) * .14 || 1;
    const mTop = MB + 20, mBot = MB + MH - 4, lo2 = mn - pad, hi2 = mx + pad;
    const MY = v => mBot - (v - lo2) / (hi2 - lo2) * (mBot - mTop), mid = MY(0), mp = k => mac.map((m, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + MY(m[k]).toFixed(1)).join("");
    g += `<line x1="${L}" x2="${L}" y1="${mTop}" y2="${mBot}" stroke="#8C9096" stroke-width="1"/>
      <line x1="${L}" x2="${W - R}" y1="${mid}" y2="${mid}" stroke="#8C9096" stroke-width="1"/>
      <text x="${W - R + 6}" y="${mid + 3.5}" font-size="10.5" fill="#9AA0A6">0</text>
      <text x="${L - 6}" y="${MY(mx) + 3.5}" font-size="10.5" fill="#9AA0A6" text-anchor="end">${fmt(mx, dec)}</text>
      <text x="${L - 6}" y="${MY(mn) + 3.5}" font-size="10.5" fill="#9AA0A6" text-anchor="end">${fmt(mn, dec)}</text>`;
    mac.forEach((m, i) => {
      const y = MY(m[3]), h = Math.max(1, Math.abs(y - mid)), up = m[3] >= 0;
      g += `<rect x="${(X(i) - vbw / 2).toFixed(1)}" y="${(up ? y : mid).toFixed(1)}" width="${vbw.toFixed(1)}" height="${h.toFixed(1)}" rx="1.5" fill="${up ? "var(--up)" : "var(--dn)"}" opacity=".5"/>
        ${dense ? "" : `<text x="${X(i)}" y="${up ? y - 4 : y + h + 11}" font-size="10" fill="#4B5158" text-anchor="middle">${fmt(m[3], dec)}</text>`}`;
    });
    g += `<path d="${mp(1)}" fill="none" stroke="var(--chart)" stroke-width="2.2" stroke-linejoin="round"/><path d="${mp(2)}" fill="none" stroke="#F59E0B" stroke-width="2.2" stroke-linejoin="round"/>`;
    if (!dense) mac.forEach((m, i) => { g += `<circle cx="${X(i)}" cy="${MY(m[1])}" r="3.5" fill="var(--chart)" stroke="#fff" stroke-width="1.2"/><circle cx="${X(i)}" cy="${MY(m[2])}" r="3.5" fill="#F59E0B" stroke="#fff" stroke-width="1.2"/>`; });
    // 交叉：柱子由負轉正＝黃金交叉、由正轉負＝死亡交叉（MACD 線穿越信號線），標在轉折那天
    mac.forEach((m, i) => {
      if (!i || (m[3] >= 0) === (mac[i - 1][3] >= 0)) return;
      const gold = m[3] >= 0, cx = (X(i) + X(i - 1)) / 2, ratio = Math.abs(mac[i - 1][3]) / (Math.abs(mac[i - 1][3]) + Math.abs(m[3])), cy = MY(mac[i - 1][1] + (m[1] - mac[i - 1][1]) * ratio);
      const px = X(i - 1) + (X(i) - X(i - 1)) * ratio, col = gold ? "var(--up)" : "var(--dn)";
      g += `<circle cx="${px}" cy="${cy}" r="${n > 30 ? 5 : 8}" fill="none" stroke="${col}" stroke-width="2"/>
        ${n > 30 ? "" : `<text x="${px}" y="${cy - 13}" font-size="11.5" font-weight="700" fill="${col}" text-anchor="middle" style="paint-order:stroke;stroke:#fff;stroke-width:3px">${gold ? "黃金交叉" : "死亡交叉"}</text>`}`;
    });
    const last = mac[n - 1], yl = MY(last[1]), ys = MY(last[2]);
    g += `<text x="${W - R + 6}" y="${yl + (Math.abs(yl - ys) < 13 ? (last[1] > last[2] ? -4 : 12) : 3.5)}" font-size="10.5" fill="var(--chart)">MACD　${fmt(last[1], dec)}</text><text x="${W - R + 6}" y="${ys + (Math.abs(yl - ys) < 13 ? (last[1] > last[2] ? 12 : -4) : 3.5)}" font-size="10.5" fill="#D97706">信號　${fmt(last[2], dec)}</text>`;
  }
  el.innerHTML = `<svg width="${W}" height="${H}" role="img" aria-label="${DD.en} 回補走勢圖與每日成交量">${g}<g id="rhov"></g><rect x="0" y="0" width="${W}" height="${H}" fill="transparent"/></svg>`;
  const svg = el.firstChild, hov = svg.querySelector("#rhov");
  // 滑鼠移到點上：該日回補水位的虛線＋浮標（浮標只有股價）；同一天的量柱加外框
  const show = i => {
    const v = pts[i][1], x = X(i), y = Y(v), txt = (hist ? short(pts[i][0]) + "　" : "") + fmt(v, dec) + mas.map(m => m.pts[i] != null ? "　" + m.label + m.n + " " + fmt(m.pts[i], dec) : "").join(""), w = txt.length * 7.6 + 18, h = 24;
    const bx = Math.max(L + 2, Math.min(W - R - w - 2, x - w / 2)), by = y - 16 - h >= T ? y - 16 - h : y + 16;
    const vb = vols && st.vol ? `<rect x="${(X(i) - vbw / 2).toFixed(1)}" y="${(vbase - barH(vols[i])).toFixed(1)}" width="${vbw.toFixed(1)}" height="${barH(vols[i]).toFixed(1)}" rx="1.5" fill="none" stroke="${ACC}" stroke-width="1.6"/>` : "";
    hov.innerHTML = `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" stroke="${ACC}" stroke-width="1.5" stroke-dasharray="3 3"/>
      <circle cx="${x}" cy="${y}" r="7" fill="none" stroke="${ACC}" stroke-width="2"/>
      <text x="${W - R - 6}" y="${y - 7}" font-size="11.5" font-weight="600" fill="${ACC}" text-anchor="end" style="paint-order:stroke;stroke:#fff;stroke-width:3px">${x + 14 < W - R - 6 - 66 ? "回補 " : ""}${fmt(pc(v), 1)}%</text>
      <g><rect x="${bx}" y="${by}" width="${w}" height="${h}" rx="6" fill="#22262B"/><text x="${bx + w / 2}" y="${by + 16.5}" font-size="13" font-weight="600" fill="#fff" text-anchor="middle">${txt}</text></g>${vb}`;
  };
  const near = e => {
    const r = svg.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top, i = Math.round((x - L) / pw);
    if (dense) return i >= 0 && i <= n - 1 && Math.abs(x - X(i)) <= pw / 2 + 3 && Math.abs(y - Y(pts[i][1])) <= 30 ? i : -1;
    return i >= 0 && i <= n - 1 && Math.hypot(x - X(i), y - Y(pts[i][1])) <= 18 ? i : -1;
  };
  const vpHit = e => {   // 滑鼠是否在 VPVR 某一條橫條上
    if (!vp) return null;
    const r = svg.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top, v = vbot + (T + PH - y) / PH * (vtop - vbot);
    return vp.bins.find(b => v >= b[0] && v < b[1] && x >= L && x <= L + vpW(b)) || null;
  };
  const showVp = b => {
    const v = (b[0] + b[1]) / 2, y = Y(v);
    hov.innerHTML = `<line x1="${L}" x2="${W - R}" y1="${y}" y2="${y}" stroke="${ACC}" stroke-width="1.5" stroke-dasharray="3 3"/>
      <text x="${L - 6}" y="${y + 3.5}" font-size="11.5" font-weight="700" fill="${ACC}" text-anchor="end" style="paint-order:stroke;stroke:#fff;stroke-width:3px">${fmt(v, dec)}</text>
      <text x="${W - R + 6}" y="${y + 3.5}" font-size="11.5" font-weight="700" fill="${ACC}" style="paint-order:stroke;stroke:#fff;stroke-width:3px">回補 ${fmt(pc(v), 1)}%</text>
      <text x="${L + vpW(b) + 6}" y="${y - 4}" font-size="11" fill="#4B5158" style="paint-order:stroke;stroke:#fff;stroke-width:3px">${fmt(b[2], 1)} 百萬股</text>`;
  };
  svg.addEventListener("pointermove", e => {
    const i = near(e), vb_ = i < 0 ? vpHit(e) : null;
    if (vb_) { svg.style.cursor = "default"; showVp(vb_); return; }
    { const yy = e.clientY - svg.getBoundingClientRect().top; svg.style.cursor = i >= 0 || bands.some(b => yy >= b[0] && yy <= b[1]) ? "pointer" : "default"; }
    if (i >= 0) show(i); else hov.innerHTML = "";
  });
  svg.addEventListener("click", e => {   // 點面板標題列：收合／展開，重畫
    const y = e.clientY - svg.getBoundingClientRect().top, b = bands.find(b => y >= b[0] && y <= b[1]);
    if (b) { st[b[2]] = !st[b[2]]; drawRetrace(el, data, leg); }
  });
  svg.addEventListener("pointerdown", e => { const i = near(e), b_ = i < 0 ? vpHit(e) : null; if (i >= 0) show(i); else if (b_) showVp(b_); else hov.innerHTML = ""; });   // 觸控螢幕：點一下顯示
  svg.addEventListener("pointerleave", e => { if (e.pointerType !== "touch") hov.innerHTML = ""; });
  leg.innerHTML = `<span><i style="background:var(--chart)"></i>每日收盤</span>${mas.map(m => { const last = [...m.pts].reverse().find(v => v != null); return `<span><i style="background:${m.c}"></i>${m.label}${m.n}（${m.n} 日均線）${last != null ? "最新 " + fmt(last, dec) : ""}</span>`; }).join("")}<span><i style="background:#6B7178;height:0;border-top:2px dashed #6B7178"></i>固定回補位（38.2% / 50% / 61.8%）</span><span><i style="background:${ACC};height:0;border-top:2px dashed ${ACC}"></i>滑鼠所在點的回補位</span>${vp ? `<span><i style="background:var(--chart);opacity:.4"></i>VPVR 成交量分布：${vm_ === "year" ? sw.vpYear.start.slice(0, 4) + " 整年（日線，只畫目前圖軸範圍內的量）" : "10/6 起（15 分 K）"}；滑鼠移到柱上顯示股價與回補位</span>` : ""}${vols ? "<span>量柱：紅漲綠跌</span>" : ""}${mac ? '<span><i style="background:#F59E0B"></i>MACD 信號線</span><span><i style="background:var(--chart)"></i>MACD 線</span><span>MACD 柱：紅正綠負</span>' : ""}${scen.map(s => `<span><i style="background:${s.color};height:0;border-top:2px dashed ${s.color}"></i>${s.label}</span>`).join("")}`;
}

// VPVR 範圍開關（格式同 amd.html）：10/6 起／2026 整年／關；每張圖各自記住選擇
const VP_SEG = id => `<div class="ctl" style="margin:0 0 8px"><span style="font-size:13px;color:var(--muted)">VPVR 範圍</span><div class="seg" data-vp="${id}"><button type="button" data-m="swing" class="on">10/6 起</button><button type="button" data-m="year">2026 整年</button><button type="button" data-m="off">關</button></div></div>`;
function bindVpSeg(redraw) {
  document.querySelectorAll(".seg[data-vp]").forEach(seg => seg.onclick = e => {
    const m = e.target.dataset && e.target.dataset.m; if (!m) return;
    (drawRetrace.vpm = drawRetrace.vpm || {})[seg.dataset.vp] = m;
    seg.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.m === m));
    redraw(seg.dataset.vp);
  });
}

// 均線開關：月線／季線／半年線／年線四個按鈕，可疊加、預設全關，每張圖各自記住；需資料有 swing.hist
const MA_DEF = [
  {k: "m", label: "月線", c: "#F08C00", tw: 20, us: 20},
  {k: "q", label: "季線", c: "#7C3AED", tw: 60, us: 50},
  {k: "h", label: "半年線", c: "#0D9488", tw: 120, us: 100},
  {k: "y", label: "年線", c: "#E11D74", tw: 240, us: 200},
];
// 台股（代號開頭是數字，如 0050）用 20/60/120/240；美股用 20/50/100/200（TradingView 預設）
const MA_SET = code => MA_DEF.map(m => ({...m, n: /^\d/.test(String(code || "")) ? m.tw : m.us}));
const MA_SEG = (id, code) => `<div class="ctl"><span style="font-size:13px;color:var(--muted)">均線</span><div class="seg" data-ma="${id}">${MA_SET(code).map(m => `<button type="button" data-k="${m.k}" aria-pressed="false"><i style="display:inline-block;width:12px;height:3px;border-radius:2px;background:${m.c};vertical-align:middle;margin-right:6px"></i>${m.label}${m.n}</button>`).join("")}</div></div>`;
function bindMaSeg(redraw) {
  document.querySelectorAll(".seg[data-ma]").forEach(seg => {
    const set = (drawRetrace.ma = drawRetrace.ma || {})[seg.dataset.ma] = new Set();
    seg.onclick = e => {
      const b = e.target.closest && e.target.closest("button"); if (!b) return;
      const k = b.dataset.k; set.has(k) ? set.delete(k) : set.add(k);
      b.classList.toggle("on", set.has(k)); b.setAttribute("aria-pressed", set.has(k));
      redraw(seg.dataset.ma);
    };
  });
}

// 時間範圍開關：1 個月／3 個月／6 個月／2026；全部不選＝回補段（預設畫面）；需資料有 swing.hist
const WIN_SEG = id => `<div class="ctl" style="margin-left:auto"><span style="font-size:13px;color:var(--muted)">時間範圍</span><div class="seg" data-win="${id}"><button type="button" data-w="1m">1 個月</button><button type="button" data-w="3m">3 個月</button><button type="button" data-w="6m">6 個月</button><button type="button" data-w="ytd">2026</button></div></div>`;
function bindWinSeg(redraw) {
  document.querySelectorAll(".seg[data-win]").forEach(seg => seg.onclick = e => {
    const w = e.target.dataset && e.target.dataset.w; if (!w) return;
    const w0 = ((drawRetrace.win = drawRetrace.win || {})[seg.dataset.win] || {mode: "swing"}).mode, m = w === w0 ? "swing" : w;   // 再點一次＝取消
    drawRetrace.win[seg.dataset.win] = {mode: m};
    seg.querySelectorAll("button").forEach(x => x.classList.toggle("on", x.dataset.w === m));
    redraw(seg.dataset.win);
  });
}
