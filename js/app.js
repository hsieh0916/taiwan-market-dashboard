/* Taiwan Market Dashboard - Main Application */
'use strict';

const DATA_URL = 'data/market_data.json';
const DATA_URL_ABS = 'https://hsieh0916.github.io/taiwan-market-dashboard/data/market_data.json';
let institutionalChart = null;
let vixtwChart = null;
let vixUsChart = null;
let vixUsHistoryData = null;

const VIX_TERM_COLORS = { vix9d: '#f44336', vix: '#ff9800', vix3m: '#2196F3', vix6m: '#9c27b0' };
const VIX_TERM_LABELS = { vix9d: 'VIX9D', vix: 'VIX', vix3m: 'VIX3M', vix6m: 'VIX6M' };

// ─── Chart.js global defaults ───────────────────────────────────────────────
Chart.defaults.color = '#8fa3bf';
Chart.defaults.borderColor = '#1e2d45';
Chart.defaults.font.family = "'Segoe UI', 'PingFang TC', 'Microsoft JhengHei', sans-serif";

// ─── Entry point ─────────────────────────────────────────────────────────────
async function loadData() {
  showLoading(true);
  let lastErr = null;
  // Try relative URL first (works on GitHub Pages); fall back to absolute URL
  // (handles cases where the page is opened via file:// or a local server)
  for (const url of [DATA_URL, DATA_URL_ABS]) {
    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      try { render(data); } catch (renderErr) { console.error('Render error:', renderErr); }
      showLoading(false);
      return;
    } catch (err) {
      console.warn(`fetch failed (${url}):`, err);
      lastErr = err;
    }
  }
  showLoading(false);
  showError(
    '無法載入市場數據。\n' +
    '請確認網路連線正常，或直接訪問 GitHub Pages：\n' +
    'https://hsieh0916.github.io/taiwan-market-dashboard/\n\n' +
    '錯誤：' + (lastErr && lastErr.message)
  );
}

function render(data) {
  const safe = (fn, name) => { try { fn(); } catch (e) { console.error(`[render:${name}]`, e); } };
  safe(() => updateHeader(data),                      'header');
  safe(() => updateKeyIndicators(data),               'keyIndicators');
  safe(() => renderHeatmaps(data.heatmap),            'heatmaps');
  safe(() => renderUsIndices(data.vix),               'usIndices');
  safe(() => renderDraiHoldings(data.drai),           'draiHoldings');
  safe(() => updateSignalBanner(data.signal),         'signalBanner');
  safe(() => renderTermStructure(data.vix),           'termStructure');
  safe(() => renderGauge(data.cnn_fear_greed),        'gauge');
  safe(() => renderInstitutionalChart(data.institutional), 'instChart');
  safe(() => renderVixCharts(data.vix_history),       'vixCharts');
  safe(() => renderSignalTable(data.signal),          'signalTable');
  safe(() => renderScanResults(data.scan),            'scanResults');
  safe(() => renderAnalysis(data.analysis, data.last_updated), 'analysis');
  safe(() => renderInstitutionalBreakdown(data.institutional), 'instBreakdown');
}

// ─── Header ──────────────────────────────────────────────────────────────────
function updateHeader(data) {
  // Derive current Taiwan time once — reused for both stale check and market status
  const now   = new Date();
  const tst   = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Taipei' }));
  const twDay = tst.getDay();           // 0=Sun, 6=Sat
  const twH   = tst.getHours();
  const twM   = tst.getMinutes();
  const twNum = twH * 100 + twM;

  const isWeekday      = twDay >= 1 && twDay <= 5;
  const isMarketHours  = isWeekday && twNum >= 900  && twNum < 1330;
  // "Active window": weekday, 09:00–18:00 TST — cron runs during this window
  const isActiveWindow = isWeekday && twNum >= 900  && twNum < 1800;

  // ── Last updated label ──
  const dt = new Date(data.last_updated || data.last_updated_utc);
  const updEl = el('lastUpdated');
  if (isNaN(dt)) {
    updEl.textContent = '—';
  } else {
    // Show date + time; add context tag when outside active window
    const dtLabel = dt.toLocaleString('zh-TW', {
      month: 'numeric', day: 'numeric',
      hour: 'numeric', minute: '2-digit',
    });
    const ageMin = (now - dt) / 60000;

    let tag = '';
    let stale = false;
    let tip = '';

    if (!isWeekday) {
      // Weekend — expected, data is from last trading day
      tag   = ' (非交易日)';
      tip   = '週末非交易日，顯示最後交易日盤後資料，下次更新於週一開盤前';
    } else if (!isActiveWindow) {
      // Weekday but outside cron window (before 9am or after 6pm)
      tag   = ' (盤後)';
      tip   = '盤後資料，下次排程更新於隔日開盤前';
    } else if (ageMin > 45) {
      // Within active window but stale — something may be wrong
      stale = true;
      tip   = `資料已超過 ${Math.floor(ageMin)} 分鐘未更新，排程可能延誤`;
    } else {
      tip = `資料更新於 ${Math.floor(ageMin)} 分鐘前`;
    }

    updEl.textContent = dtLabel + tag;
    const updateRow = el('update-time');
    if (updateRow) {
      updateRow.classList.toggle('update-stale', stale);
      updateRow.title = tip;
    }
  }

  // ── Market status dot ──
  const isOpen = isMarketHours;
  const dot = el('statusDot');
  dot.className = `status-dot ${isOpen ? 'open' : 'closed'}`;
  el('statusText').textContent = isOpen ? '台灣市場交易中'
    : !isWeekday ? '週末休市'
    : twNum < 900 ? '開盤前'
    : '盤後';
}

// ─── Key Indicators ───────────────────────────────────────────────────────────
function updateKeyIndicators(data) {
  const vix = data.vix || {};
  const cnn = data.cnn_fear_greed || {};
  const inst = data.institutional || {};

  // TWII
  updatePriceCard('twii', vix.twii, '', '點');
  renderMaRow('twii', vix.twii);
  renderVolRow('twii', vix.twii);

  // TPEX 櫃買指數
  updatePriceCard('tpex', vix.tpex, '', '點');
  renderMaRow('tpex', vix.tpex);
  renderVolRow('tpex', vix.tpex);

  // VIXTWN
  if (vix.vixtwn) {
    updatePriceCard('vixtwn', vix.vixtwn, '', '');
    el('vixtwn-badge').textContent = vixLevel(vix.vixtwn.current).label;
    el('vixtwn-badge').className = `card-badge ${vixLevel(vix.vixtwn.current).cls}`;
  }

  // US VIX
  if (vix.vix) {
    updatePriceCard('vix', vix.vix, '', '');
    const lvl = vixUsLevel(vix.vix.current);
    el('vix-badge').textContent = lvl.label;
    el('vix-badge').className = `card-badge ${lvl.cls}`;
  }

  // CNN
  if (cnn.current != null) {
    el('cnn-value').textContent = cnn.current.toFixed(1);
    const cnnLvl = cnnLevel(cnn.current);
    el('cnn-rating').textContent = cnnLvl.zh;
    el('cnn-rating').className = cnnLvl.changeClass;
    el('cnn-badge').textContent = cnnLvl.zh;
    el('cnn-badge').className = `card-badge ${cnnLvl.cls}`;
  }

  // Institutions
  if (inst.total_net != null) {
    const b = inst.total_net / 100000000;
    el('inst-value').textContent = (b >= 0 ? '+' : '') + b.toFixed(1) + ' 億';
    el('inst-value').className = `card-value ${b >= 0 ? 'change-up' : 'change-down'}`;
    const parts = [];
    if (inst.foreign != null) parts.push(`外資 ${fmtBil(inst.foreign)}`);
    if (inst.investment_trust != null) parts.push(`投信 ${fmtBil(inst.investment_trust)}`);
    if (inst.dealer != null) parts.push(`自營 ${fmtBil(inst.dealer)}`);
    el('inst-sub').textContent = parts.join(' | ');
  }
}

// ─── US Major Indices ─────────────────────────────────────────────────────────
function renderUsIndices(vix) {
  if (!vix) return;
  [
    { id: 'sp500',  key: 'sp500'  },
    { id: 'nasdaq', key: 'nasdaq' },
    { id: 'dji',    key: 'dji'   },
    { id: 'sox',    key: 'sox'   },
    { id: 'nikkei', key: 'nikkei' },
    { id: 'kospi',  key: 'kospi'  },
  ].forEach(({ id, key }) => {
    const t = vix[key];
    if (!t || t.current == null) return;
    updatePriceCard(id, t, '', '');
    const badge = el(`${id}-badge`);
    if (badge && t.change_pct != null) {
      const up = t.change_pct > 0;
      badge.textContent = (up ? '▲ ' : '▼ ') + Math.abs(t.change_pct).toFixed(2) + '%' + (t.gap_warning ? ' ⚠' : '');
      badge.className = `card-badge ${up ? 'badge--bull' : 'badge--bear'}`;
      badge.title = t.gap_warning
        ? `資料來源缺漏交易日（${t.prev_date} → ${t.data_date}），漲跌幅跨多個交易日，非單日變動`
        : '';
    }
    renderMaRow(id, t);
  });

  // Show data date label when US market data is from a previous session
  const dateEl = el('us-data-date');
  if (dateEl && vix.sp500 && vix.sp500.data_date) {
    const dataDate = vix.sp500.data_date; // "YYYY-MM-DD"
    // Convert to Taiwan local date string for comparison
    const tst = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Taipei' }));
    const todayTST = `${tst.getFullYear()}-${String(tst.getMonth()+1).padStart(2,'0')}-${String(tst.getDate()).padStart(2,'0')}`;
    if (dataDate !== todayTST) {
      const [y, m, d] = dataDate.split('-');
      dateEl.textContent = `資料截至 ${m}/${d}`;
      dateEl.style.display = '';
    } else {
      dateEl.style.display = 'none';
    }
  }
}

function renderVolRow(id, t) {
  const row = el(`${id}-vol`);
  if (!row || !t || t.volume_ratio == null) return;
  const pct = t.volume_ratio;
  const cls = pct >= 80 ? 'vol-high' : pct >= 40 ? 'vol-mid' : 'vol-low';
  const bar = Math.round(pct);
  row.innerHTML =
    `<span class="vol-label">成交量</span>` +
    `<span class="vol-bar-wrap"><span class="vol-bar ${cls}" style="width:${bar}%"></span></span>` +
    `<span class="vol-pct ${cls}">${pct.toFixed(0)}%</span>` +
    `<span class="vol-hint">近60日最大</span>`;
}

function renderMaRow(id, t) {
  const row = el(`${id}-ma`);
  if (!row || !t) return;
  const items = [
    { label: '月線', val: t.ma20_diff_pct },
    { label: '季線', val: t.ma60_diff_pct },
    { label: '年線', val: t.ma240_diff_pct },
    { label: '近高', val: t.high_recent_diff_pct },
  ];
  row.innerHTML = items.map(({ label, val }) => {
    if (val == null) return '';
    const up = val >= 0;
    const cls = up ? 'ma-item--up' : 'ma-item--down';
    const sign = up ? '+' : '';
    return `<span class="ma-item ${cls}"><span class="ma-label">${label}</span><span class="ma-val">${sign}${val.toFixed(1)}%</span></span>`;
  }).join('');
}

function renderDraiHoldings(drai) {
  const chips = el('drai-chips');
  const asOf  = el('drai-as-of');
  if (!chips) return;
  if (!drai || !drai.holdings || !drai.holdings.length) {
    chips.innerHTML = '<span class="drai-loading">資料暫無</span>';
    return;
  }
  if (asOf) asOf.textContent = drai.as_of ? `As of ${drai.as_of}` : '—';
  chips.innerHTML = drai.holdings.map(h => {
    const w = h.weight;
    const cls = w >= 15 ? 'drai-chip--lg' : w >= 5 ? 'drai-chip--md' : 'drai-chip--sm';
    return `<span class="drai-chip ${cls}"><span class="drai-ticker">${h.ticker}</span><span class="drai-w">${w.toFixed(2)}%</span></span>`;
  }).join('');
}

function updatePriceCard(id, ticker, prefix, suffix) {
  if (!ticker) return;
  const val = ticker.current;
  if (val == null) { el(`${id}-value`).textContent = 'N/A'; return; }

  el(`${id}-value`).textContent = prefix + fmtNum(val) + suffix;

  if (ticker.change != null) {
    const sign = ticker.change >= 0 ? '+' : '';
    const cls = ticker.change > 0 ? 'change-up' : ticker.change < 0 ? 'change-down' : 'change-flat';
    const changeEl = el(`${id}-change`);
    changeEl.textContent = `${sign}${ticker.change.toFixed(2)} (${sign}${ticker.change_pct?.toFixed(2)}%)`
      + (ticker.gap_warning ? ' ⚠' : '');
    changeEl.className = `card-change ${cls}`;
    changeEl.title = ticker.gap_warning
      ? `資料來源缺漏交易日（${ticker.prev_date} → ${ticker.data_date}），漲跌幅跨多個交易日，非單日變動`
      : '';
  }
}

// ─── Signal Banner ────────────────────────────────────────────────────────────
function updateSignalBanner(signal) {
  if (!signal) return;
  const score = signal.score;
  el('signalScore').textContent = (score >= 0 ? '+' : '') + score.toFixed(1);
  el('signalScore').style.color = signal.color;
  el('outlookEn').textContent = signal.outlook_en;
  el('outlookEn').style.color = signal.color;
  el('outlookZh').textContent = signal.outlook;

  // Position the bar needle: score maps -100→0%, +100→100%
  const pct = ((score + 100) / 200) * 100;
  el('signalBarFill').style.left = `${Math.max(2, Math.min(98, pct))}%`;
}

// ─── VIX Term Structure ───────────────────────────────────────────────────────
function renderTermStructure(vix) {
  if (!vix) return;
  const terms = [
    { key: 'vix9d',  label: 'VIX9D\n超短期', color: '#f44336' },
    { key: 'vix',    label: 'VIX\n短期',    color: '#ff9800' },
    { key: 'vix3m',  label: 'VIX3M\n中期',  color: '#2196F3' },
    { key: 'vix6m',  label: 'VIX6M\n長期',  color: '#9c27b0' },
  ];

  const values = terms.map(t => vix[t.key]?.current).filter(v => v != null);
  const maxVal = Math.max(...values, 1);

  const container = el('termStructureBars');
  container.innerHTML = '';

  terms.forEach(t => {
    const val = vix[t.key]?.current;
    if (val == null) return;
    const pct = (val / (maxVal * 1.3)) * 100;
    const div = document.createElement('div');
    div.className = 'term-bar-item';
    div.innerHTML = `
      <div class="term-bar-value" style="color:${t.color}">${val.toFixed(2)}</div>
      <div class="term-bar-col-wrap">
        <div class="term-bar-col" style="height:${pct}%;background:${t.color};opacity:0.85"></div>
      </div>
      <div class="term-bar-label">${t.label.replace('\n', '<br>')}</div>
    `;
    container.appendChild(div);
  });

  // Detect contango vs backwardation
  const v9d = vix.vix9d?.current;
  const v1m = vix.vix?.current;
  const v3m = vix.vix3m?.current;

  const tag = el('termStructureTag');
  const note = el('termStructureNote');

  if (v9d && v1m) {
    if (v9d > v1m * 1.05) {
      tag.textContent = '倒掛 Backwardation';
      tag.className = 'chart-card-tag backwardation';
      note.textContent = `VIX期限結構倒掛：短期波動恐慌（VIX9D ${v9d.toFixed(2)}）高於現貨VIX（${v1m.toFixed(2)}），顯示投資人對近期擔憂遠大於中長期，歷史上常為恐慌性底部訊號。`;
    } else if (v9d < v1m * 0.97) {
      tag.textContent = '順向 Contango';
      tag.className = 'chart-card-tag contango';
      note.textContent = `VIX期限結構正常順向：超短期波動（VIX9D ${v9d.toFixed(2)}）低於現貨VIX（${v1m.toFixed(2)}），市場近期相對平靜，中期不確定性較高，整體屬正常市場狀態。`;
    } else {
      tag.textContent = '趨近平坦';
      tag.className = 'chart-card-tag';
      note.textContent = `VIX期限結構接近平坦，短中期市場不確定性相近，方向不明確，需觀察突破方向。`;
    }
  }
}

// ─── CNN Gauge (pure Canvas, CNN colour scheme + correct needle direction) ────
// CNN colour map: left=Extreme Fear (dark red) → right=Extreme Greed (dark green)
// Angle convention: 0-score maps to π…2π  (9 o'clock → 12 o'clock → 3 o'clock)
const CNN_SEGS = [
  { s: 0,  e: 25,  color: '#b22222' },   // Extreme Fear – dark red
  { s: 25, e: 45,  color: '#e05a28' },   // Fear          – orange-red
  { s: 45, e: 55,  color: '#f5c518' },   // Neutral       – gold
  { s: 55, e: 75,  color: '#8bc34a' },   // Greed         – yellow-green
  { s: 75, e: 100, color: '#2e7d32' },   // Extreme Greed – forest green
];

function cnnSegColor(score) {
  const seg = CNN_SEGS.find(s => score <= s.e) || CNN_SEGS[CNN_SEGS.length - 1];
  return seg.color;
}

function renderGauge(cnn) {
  if (!cnn || cnn.current == null) return;
  const score = cnn.current;
  const lvl   = cnnLevel(score);

  // Show data's own timestamp so users can see it's not live
  const tsEl = el('cnnDataTs');
  if (tsEl && cnn.data_timestamp) {
    try {
      const dt = new Date(cnn.data_timestamp);
      const hhmm = dt.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit', timeZone: 'America/New_York', hour12: false });
      tsEl.textContent = `資料截至 ET ${hhmm}`;
      tsEl.style.display = '';
    } catch (_) {}
  }

  const canvas = document.getElementById('gaugeChart');
  const ctx    = canvas.getContext('2d');
  const W = canvas.width;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const cx     = W / 2;
  const cy     = H - 6;              // pivot at bottom edge (flat of semicircle)
  const outerR = Math.min(cx - 4, H - 10);
  const innerR = outerR * 0.58;      // 58% cutout → CNN-width arc

  // ── 1. Dark background ring (matches card bg, creates thin gap effect) ──
  ctx.beginPath();
  ctx.arc(cx, cy, outerR + 3, Math.PI, 2 * Math.PI, false);
  ctx.arc(cx, cy, innerR - 3, 2 * Math.PI, Math.PI, true);
  ctx.closePath();
  ctx.fillStyle = '#080c18';
  ctx.fill();

  // ── 2. Coloured arc segments ──
  CNN_SEGS.forEach(seg => {
    const a1 = Math.PI * (1 + seg.s  / 100);
    const a2 = Math.PI * (1 + seg.e  / 100);
    ctx.beginPath();
    ctx.arc(cx, cy, outerR, a1, a2, false);   // outer arc CW
    ctx.arc(cx, cy, innerR, a2, a1, true);    // inner arc CCW
    ctx.closePath();
    ctx.fillStyle = seg.color;
    ctx.fill();
  });

  // ── 3. Thin dark dividers between zones ──
  [0, 25, 45, 55, 75, 100].forEach(p => {
    const a  = Math.PI * (1 + p / 100);
    ctx.beginPath();
    ctx.moveTo(cx + (innerR - 1) * Math.cos(a), cy + (innerR - 1) * Math.sin(a));
    ctx.lineTo(cx + (outerR + 1) * Math.cos(a), cy + (outerR + 1) * Math.sin(a));
    ctx.strokeStyle = '#080c18';
    ctx.lineWidth   = 2.5;
    ctx.stroke();
  });

  // ── 4. Small tick marks at 0/25/50/75/100 ──
  [0, 25, 50, 75, 100].forEach(p => {
    const a   = Math.PI * (1 + p / 100);
    const r1  = outerR + 4;
    const r2  = outerR + 10;
    ctx.beginPath();
    ctx.moveTo(cx + r1 * Math.cos(a), cy + r1 * Math.sin(a));
    ctx.lineTo(cx + r2 * Math.cos(a), cy + r2 * Math.sin(a));
    ctx.strokeStyle = 'rgba(255,255,255,0.35)';
    ctx.lineWidth   = 1.5;
    ctx.stroke();

    // Numeric labels (0 / 25 / 50 / 75 / 100)
    const labelR = outerR + 20;
    const lx = cx + labelR * Math.cos(a);
    const ly = cy + labelR * Math.sin(a);
    ctx.save();
    ctx.font         = '9px "Roboto Mono", monospace';
    ctx.fillStyle    = 'rgba(255,255,255,0.38)';
    ctx.textAlign    = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(p, lx, ly);
    ctx.restore();
  });

  // ── 5. Inner cutout fill (score + rating text live here) ──
  ctx.beginPath();
  ctx.arc(cx, cy, innerR - 3, Math.PI, 2 * Math.PI, false);
  ctx.closePath();
  ctx.fillStyle = '#111827';
  ctx.fill();

  // ── 6. Score & rating text inside the cutout ──
  const scoreY  = cy - innerR * 0.52;
  const ratingY = cy - innerR * 0.22;

  ctx.save();
  ctx.textAlign    = 'center';
  ctx.textBaseline = 'middle';

  ctx.font      = `bold ${Math.round(outerR * 0.32)}px -apple-system, "Segoe UI", sans-serif`;
  ctx.fillStyle = cnnSegColor(score);
  ctx.fillText(score.toFixed(0), cx, scoreY);

  ctx.font      = `600 ${Math.round(outerR * 0.125)}px -apple-system, "Segoe UI", sans-serif`;
  ctx.fillStyle = 'rgba(200,215,235,0.85)';
  ctx.fillText(lvl.zh, cx, ratingY);
  ctx.restore();

  // ── 7. Needle (triangle) – correct angle: π + score/100 × π ──
  const needleAngle = Math.PI * (1 + score / 100);
  const needleLen   = outerR * 0.76;
  const nx  = cx + needleLen * Math.cos(needleAngle);
  const ny  = cy + needleLen * Math.sin(needleAngle);
  const perpA = needleAngle + Math.PI / 2;
  const base  = 5;

  ctx.beginPath();
  ctx.moveTo(nx, ny);
  ctx.lineTo(cx + base * Math.cos(perpA), cy + base * Math.sin(perpA));
  ctx.lineTo(cx - base * Math.cos(perpA), cy - base * Math.sin(perpA));
  ctx.closePath();
  ctx.fillStyle    = '#ffffff';
  ctx.shadowColor  = 'rgba(0,0,0,0.6)';
  ctx.shadowBlur   = 4;
  ctx.fill();
  ctx.shadowBlur   = 0;

  // ── 8. Pivot hub ──
  ctx.beginPath();
  ctx.arc(cx, cy, 8, 0, 2 * Math.PI);
  ctx.fillStyle   = '#ffffff';
  ctx.fill();
  ctx.beginPath();
  ctx.arc(cx, cy, 5, 0, 2 * Math.PI);
  ctx.fillStyle   = '#1a2435';
  ctx.fill();

  // ── 9. History comparison row ──
  const histItems = [
    { label: '昨日', value: cnn.prev_close },
    { label: '上週', value: cnn.prev_1week },
    { label: '上月', value: cnn.prev_1month },
    { label: '去年', value: cnn.prev_1year },
  ];
  const row = el('cnnHistoryRow');
  row.innerHTML = histItems.map(item => {
    const v      = item.value;
    const change = v != null ? (score - v).toFixed(1) : null;
    const cls    = change > 0 ? 'change-up' : change < 0 ? 'change-down' : 'change-flat';
    return `
      <div class="gauge-hist-item">
        <div class="gauge-hist-label">${item.label}</div>
        <div class="gauge-hist-value">${v != null ? v.toFixed(0) : '—'}</div>
        ${change != null ? `<div class="gauge-hist-label ${cls}">${change > 0 ? '+' : ''}${change}</div>` : ''}
      </div>`;
  }).join('');
}

// ─── Institutional Chart ──────────────────────────────────────────────────────
function renderInstitutionalChart(inst) {
  if (!inst || !inst.history || inst.history.length === 0) return;

  const history = inst.history;
  const labels = history.map(d => d.date.slice(4, 6) + '/' + d.date.slice(6, 8));
  const toBil = arr => arr.map(v => +(v / 100000000).toFixed(1));

  const foreign  = toBil(history.map(d => d.foreign || 0));
  const invTrust = toBil(history.map(d => d.investment_trust || 0));
  const dealer   = toBil(history.map(d => d.dealer || 0));
  const total    = toBil(history.map(d => d.total || 0));

  const ctx = document.getElementById('institutionalChart').getContext('2d');
  if (institutionalChart) institutionalChart.destroy();

  institutionalChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label: '外資',
          data: foreign,
          backgroundColor: foreign.map(v => v >= 0 ? 'rgba(33,150,243,0.7)' : 'rgba(33,150,243,0.4)'),
          borderColor: '#2196F3',
          borderWidth: 1,
          borderRadius: 3,
        },
        {
          label: '投信',
          data: invTrust,
          backgroundColor: invTrust.map(v => v >= 0 ? 'rgba(76,175,80,0.7)' : 'rgba(76,175,80,0.4)'),
          borderColor: '#4CAF50',
          borderWidth: 1,
          borderRadius: 3,
        },
        {
          label: '自營商',
          data: dealer,
          backgroundColor: dealer.map(v => v >= 0 ? 'rgba(255,152,0,0.7)' : 'rgba(255,152,0,0.4)'),
          borderColor: '#FF9800',
          borderWidth: 1,
          borderRadius: 3,
        },
        {
          label: '合計',
          data: total,
          type: 'line',
          borderColor: '#E91E63',
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: '#E91E63',
          tension: 0.3,
          yAxisID: 'y',
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y >= 0 ? '+' : ''}${ctx.parsed.y.toFixed(1)} 億`,
          },
        },
      },
      scales: {
        x: { grid: { color: '#1e2d45' }, stacked: false },
        y: {
          grid: { color: '#1e2d45' },
          ticks: { callback: v => v.toFixed(0) + '億' },
        },
      },
    },
  });
}

// ─── VIX Historical Charts ───────────────────────────────────────────────────
function renderVixCharts(history) {
  if (!history) return;

  const vixtwnDates = (history.vixtwn && history.vixtwn.dates) ? history.vixtwn.dates : [];
  const dayCount = vixtwnDates.length;

  const tag = el('vixtwHistoryTag');
  const note = el('vixtwnAccumNote');
  if (tag && dayCount > 0) {
    tag.textContent = `已累積 ${dayCount} 日`;
    tag.style.display = '';
  }
  if (note) {
    note.style.display = dayCount < 10 ? '' : 'none';
  }

  renderLineChart('vixtwChart', vixtwChart, history.vixtwn, '台灣VIX', '#00b0ff', [15, 20, 25]);
  vixtwChart = lastChart;

  vixUsHistoryData = {
    vix9d: history.vix9d,
    vix:   history.vix,
    vix3m: history.vix3m,
    vix6m: history.vix6m,
  };
  renderVixTermChart();
}

// ─── VIX Term Structure Multi-Line Chart (checkbox-toggled) ──────────────────
function renderVixTermChart() {
  if (!vixUsHistoryData) return;
  const toggle = el('vixTermToggle');
  const checked = toggle
    ? Array.from(toggle.querySelectorAll('input[type="checkbox"]:checked')).map(cb => cb.value)
    : Object.keys(VIX_TERM_COLORS);

  let labels = null;
  const datasets = [];
  checked.forEach(key => {
    const series = vixUsHistoryData[key];
    if (!series || !series.dates || series.dates.length === 0) return;
    if (!labels) labels = series.dates.map(d => d.slice(5));
    datasets.push({
      label: VIX_TERM_LABELS[key] || key,
      data: series.closes,
      borderColor: VIX_TERM_COLORS[key] || '#8fa3bf',
      backgroundColor: 'transparent',
      borderWidth: 2,
      fill: false,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0.3,
    });
  });

  if (vixUsChart) { vixUsChart.destroy(); vixUsChart = null; }
  if (!labels || datasets.length === 0) return;

  const ctx = document.getElementById('vixUsChart').getContext('2d');
  vixUsChart = new Chart(ctx, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(2)}` } },
      },
      scales: {
        x: { grid: { color: '#1e2d45' }, ticks: { maxTicksLimit: 10 } },
        y: { grid: { color: '#1e2d45' } },
      },
    },
  });
}

let lastChart = null;

function renderLineChart(canvasId, existingChart, data, label, color, thresholds) {
  if (!data || !data.dates || data.dates.length === 0) return;
  if (existingChart) existingChart.destroy();

  const ctx = document.getElementById(canvasId).getContext('2d');
  const dates = data.dates.map(d => d.slice(5));
  const values = data.closes;
  const fewPoints = dates.length < 10;

  const annotations = {};
  const thresholdColors = ['#ffc107', '#ff7043', '#f44336'];
  thresholds.forEach((t, i) => {
    annotations[`line${i}`] = {
      type: 'line',
      yMin: t,
      yMax: t,
      borderColor: thresholdColors[i] + '66',
      borderWidth: 1,
      borderDash: [4, 4],
      label: {
        display: true,
        content: String(t),
        position: 'end',
        color: thresholdColors[i],
        font: { size: 10 },
        backgroundColor: 'transparent',
        padding: 2,
      },
    };
  });

  lastChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: dates,
      datasets: [{
        label,
        data: values,
        borderColor: color,
        backgroundColor: color + '22',
        borderWidth: 2,
        fill: true,
        pointRadius: fewPoints ? 4 : 0,
        pointHoverRadius: 5,
        tension: 0.3,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        annotation: { annotations },
        tooltip: { callbacks: { label: ctx => `${label}: ${ctx.parsed.y.toFixed(2)}` } },
      },
      scales: {
        x: { grid: { color: '#1e2d45' }, ticks: { maxTicksLimit: 10 } },
        y: { grid: { color: '#1e2d45' } },
      },
    },
  });
}

// ─── Signal Details Table ────────────────────────────────────────────────────
function renderSignalTable(signal) {
  if (!signal || !signal.details) return;
  const tbody = el('signalTableBody');
  tbody.innerHTML = signal.details.map(d => {
    const s = d.signal;
    const cls = s > 10 ? 'signal-positive' : s < -10 ? 'signal-negative' : 'signal-neutral';
    const barWidth = Math.min(80, Math.abs(s)) + '%';
    const barColor = s > 0 ? '#f44336' : s < 0 ? '#00c853' : '#ffc107';
    return `<tr>
      <td><strong>${d.indicator}</strong></td>
      <td style="font-variant-numeric:tabular-nums">${typeof d.value === 'number' ? (d.value % 1 === 0 ? d.value : d.value.toFixed(2)) : d.value}</td>
      <td>
        <span class="signal-strength-bar" style="width:${barWidth};background:${barColor}"></span>
        <span class="${cls} signal-strength-num">${s >= 0 ? '+' : ''}${s}</span>
      </td>
      <td style="color:#8fa3bf">${d.weight}</td>
      <td style="color:#8fa3bf;font-size:0.82rem">${d.label}</td>
    </tr>`;
  }).join('');
}

// ─── Expert Analysis ─────────────────────────────────────────────────────────
function renderAnalysis(text, timestamp) {
  el('analysisText').textContent = text || '分析數據尚未生成。';
  if (timestamp) {
    const dt = new Date(timestamp);
    el('analysisTime').textContent = isNaN(dt) ? '' : '生成於 ' + dt.toLocaleString('zh-TW');
  }
}

// ─── Institutional Breakdown ─────────────────────────────────────────────────
function renderInstitutionalBreakdown(inst) {
  if (!inst) return;
  el('instDate').textContent = inst.date ? formatInstDate(inst.date) : '—';

  const items = [
    { name: '外資 Foreign',           value: inst.foreign,           note: '台股最大影響力' },
    { name: '投信 Investment Trust',  value: inst.investment_trust,  note: '國內基金動向' },
    { name: '自營商 Dealer',          value: inst.dealer,            note: '短線交易參考' },
    { name: '三大法人合計',           value: inst.total_net,         note: '綜合方向' },
  ];

  el('instBreakdown').innerHTML = items.map(item => {
    const val = item.value;
    if (val == null) return '';
    const b = val / 100000000;
    const cls = b >= 0 ? 'inst-positive' : 'inst-negative';
    const sign = b >= 0 ? '+' : '';
    return `<div class="inst-item">
      <div class="inst-item-name">${item.name}</div>
      <div class="inst-item-value ${cls}">${sign}${b.toFixed(1)} 億</div>
      <div class="inst-item-sub">${item.note}</div>
    </div>`;
  }).join('');
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function el(id) { return document.getElementById(id); }

function fmtNum(v) {
  if (v >= 10000) return v.toLocaleString('zh-TW', { maximumFractionDigits: 0 });
  if (v >= 100)   return v.toFixed(2);
  return v.toFixed(2);
}

function fmtBil(v) {
  const b = v / 100000000;
  return (b >= 0 ? '+' : '') + b.toFixed(1) + '億';
}

function formatInstDate(s) {
  if (!s || s.length < 8) return s;
  return `${s.slice(0,4)}/${s.slice(4,6)}/${s.slice(6,8)}`;
}

function vixLevel(v) {
  if (v == null) return { label: '—', cls: '' };
  if (v >= 30) return { label: '極度恐慌', cls: 'badge--panic' };
  if (v >= 25) return { label: '恐慌', cls: 'badge--extreme-fear' };
  if (v >= 20) return { label: '偏高', cls: 'badge--fear' };
  if (v >= 15) return { label: '正常', cls: 'badge--normal' };
  if (v >= 12) return { label: '偏低', cls: 'badge--low' };
  return { label: '極低', cls: 'badge--extreme-greed' };
}

function vixUsLevel(v) {
  if (v == null) return { label: '—', cls: '' };
  if (v >= 35) return { label: '極度恐慌', cls: 'badge--panic' };
  if (v >= 25) return { label: '偏高', cls: 'badge--fear' };
  if (v >= 18) return { label: '正常', cls: 'badge--normal' };
  if (v >= 13) return { label: '偏低', cls: 'badge--low' };
  return { label: '市場自滿', cls: 'badge--extreme-greed' };
}

function cnnLevel(v) {
  if (v == null) return { zh: '—', cls: '', color: '#8fa3bf', changeClass: 'change-flat' };
  if (v <= 25) return { zh: '極度恐懼', cls: 'badge--extreme-fear',  color: '#f44336', changeClass: 'change-down' };
  if (v <= 45) return { zh: '恐懼',     cls: 'badge--fear',          color: '#ff7043', changeClass: 'change-down' };
  if (v <= 55) return { zh: '中性',     cls: 'badge--neutral',       color: '#ffc107', changeClass: 'change-flat' };
  if (v <= 75) return { zh: '貪婪',     cls: 'badge--greed',         color: '#69f0ae', changeClass: 'change-up' };
  return              { zh: '極度貪婪', cls: 'badge--extreme-greed', color: '#00e676', changeClass: 'change-up' };
}

// ─── Taiwan Stock Heatmaps ───────────────────────────────────────────────────
const _hmCharts = {};

function heatColor(pct) {
  const c = Math.max(-7, Math.min(7, pct || 0));
  if (c > 0) {
    // 漲：紅色
    const t = c / 7;
    return `rgb(${Math.round(60+(244-60)*t)},${Math.round(15+(67-15)*t)},${Math.round(15+(54-15)*t)})`;
  }
  if (c < 0) {
    // 跌：綠色
    const t = -c / 7;
    return `rgb(${Math.round(17+(0-17)*t)},${Math.round(94+(230-94)*t)},${Math.round(35+(118-35)*t)})`;
  }
  return 'rgb(35,52,70)';
}

// ─── Heatmap external HTML tooltip (supports clickable links) ────────────────
let _hmTipTimer = null;
const _hmTip = (() => {
  const t = document.createElement('div');
  t.id = 'hm-tip';
  t.style.cssText = [
    'position:fixed','z-index:9999','display:none','pointer-events:auto',
    'background:#0c1a30','border:1px solid #1e3a6e','border-radius:10px',
    'padding:12px 15px','min-width:190px','max-width:240px',
    'font-size:13px','line-height:1.65','color:#b8cfe0',
    'box-shadow:0 8px 32px rgba(0,0,0,0.65)',
  ].join(';');
  t.addEventListener('mouseenter', () => clearTimeout(_hmTipTimer));
  t.addEventListener('mouseleave', () => { t.style.display = 'none'; });
  document.body.appendChild(t);
  return t;
})();

function _hmTipShow(chart, tooltip) {
  if (tooltip.opacity === 0) {
    _hmTipTimer = setTimeout(() => { _hmTip.style.display = 'none'; }, 180);
    return;
  }
  clearTimeout(_hmTipTimer);

  const d = tooltip.dataPoints?.[0]?.raw?._data;
  if (!d) { _hmTip.style.display = 'none'; return; }

  const sign  = (d.change_pct || 0) >= 0 ? '+' : '';
  const color = (d.change_pct || 0) >= 0 ? '#f44336' : '#00c853';
  const url   = `https://www.wantgoo.com/stock/${d.code}`;

  _hmTip.innerHTML = `
    <div style="font-size:14px;font-weight:700;color:#e6f2ff;margin-bottom:7px">
      ${d.name}<span style="font-weight:400;font-size:12px;color:#4a7fa5;margin-left:6px">${d.code}</span>
    </div>
    <div>漲跌&ensp;<b style="color:${color}">${sign}${d.change_pct ?? 0}%</b></div>
    <div>收盤&ensp;<span style="color:#ddeeff">${d.close?.toLocaleString() ?? '—'} 元</span></div>
    <div>市值&ensp;<span style="color:#ddeeff">${d.cap > 0 ? d.cap.toLocaleString() + ' 億' : '—'}</span></div>
    <div style="margin-bottom:10px">成交額&ensp;<span style="color:#ddeeff">${d.vol?.toLocaleString() ?? '—'} 億</span></div>
    <a href="${url}" target="_blank" rel="noopener noreferrer"
       style="display:block;text-align:center;background:#08162e;
              color:#00b4ff;text-decoration:none;padding:5px 0;
              border-radius:6px;border:1px solid #1e3a6e;font-size:12px;
              transition:background .15s">
      玩股網查看 ↗
    </a>`;

  _hmTip.style.display = 'block';

  const rect = chart.canvas.getBoundingClientRect();
  let x = rect.left + tooltip.caretX + 18;
  let y = rect.top  + tooltip.caretY - _hmTip.offsetHeight / 2;
  if (x + _hmTip.offsetWidth  > window.innerWidth  - 8) x = rect.left + tooltip.caretX - _hmTip.offsetWidth - 18;
  if (y + _hmTip.offsetHeight > window.innerHeight - 8) y = window.innerHeight - _hmTip.offsetHeight - 8;
  if (y < 8) y = 8;
  _hmTip.style.left = x + 'px';
  _hmTip.style.top  = y + 'px';
}

function buildHeatmap(canvasId, stocks, sizeKey, label) {
  const canvas = el(canvasId);
  if (!canvas) return;
  const existing = Chart.getChart(canvas);
  if (existing) existing.destroy();

  const items = stocks.filter(s => (s[sizeKey] || 0) > 0);
  if (!items.length) {
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
    return;
  }

  _hmCharts[canvasId] = new Chart(canvas.getContext('2d'), {
    type: 'treemap',
    data: {
      datasets: [{
        label,
        tree: items,
        key: sizeKey,
        labels: {
          display: true,
          font: [{ size: 12, weight: '600' }, { size: 10 }],
          color: ['#fff', '#ddeeff'],
          formatter(ctx) {
            if (ctx.type !== 'data') return '';
            const d = ctx.raw?._data;
            if (!d) return '';
            const sign = (d.change_pct || 0) >= 0 ? '+' : '';
            return [d.name || d.code || '', `${sign}${d.change_pct ?? 0}%`];
          },
        },
        backgroundColor(ctx) {
          if (ctx.type !== 'data') return 'transparent';
          return heatColor(ctx.raw?._data?.change_pct);
        },
        borderColor: '#0d1424',
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: false,
          external: ({ chart, tooltip }) => _hmTipShow(chart, tooltip),
        },
      },
    },
  });
}

// ─── Daily Post-Market Stock Scan ────────────────────────────────────────────
function renderScanResults(scan) {
  const asOf = el('scan-as-of');
  const list = el('scan-list');
  if (!list) return;

  if (!scan || !scan.candidates || scan.candidates.length === 0) {
    if (asOf && scan && scan.as_of) asOf.textContent = scan.as_of;
    list.innerHTML = '<div class="scan-empty">暫無符合條件的候選股（盤後資料更新後顯示）</div>';
    return;
  }

  if (asOf) {
    asOf.textContent = (scan.is_cached ? '最近一次掃描：' : '掃描時間：') + scan.as_of;
    if (scan.is_cached) {
      asOf.style.cssText = 'background:rgba(255,180,0,0.15);border:1px solid rgba(255,180,0,0.35);border-radius:4px;padding:1px 7px;';
    }
  }

  const rows = scan.candidates.map((c, i) => {
    const up  = c.change_pct > 0;
    const dn  = c.change_pct < 0;
    const cls = up ? 'change-up' : dn ? 'change-down' : '';
    const sgn = up ? '+' : '';
    const pct = Math.min(100, c.total_score);
    const barColor = c.total_score >= 65 ? 'var(--red)'
                   : c.total_score >= 45 ? 'var(--yellow)'
                   : 'var(--text-muted)';

    const sigs = (c.signals || [])
      .map(s => `<span class="scan-sig">${s}</span>`)
      .join('');

    return `
      <div class="scan-item">
        <div class="scan-item-top">
          <span class="scan-rank">${i + 1}</span>
          <div class="scan-stock">
            <a class="scan-code"
               href="https://www.wantgoo.com/stock/${c.code}/technical-chart"
               target="_blank" rel="noopener">${c.code}</a>
            <span class="scan-name">${c.name}</span>
          </div>
          <div class="scan-price">
            <span class="scan-close">${c.close.toLocaleString()}</span>
            <span class="${cls}">${sgn}${c.change_pct.toFixed(2)}%</span>
          </div>
          <div class="scan-score-block">
            <div class="scan-bar-bg">
              <div class="scan-bar-fill" style="width:${pct}%;background:${barColor}"></div>
            </div>
            <div class="scan-score-row">
              <span class="scan-score-item s-tech" title="技術面">技 ${c.tech_score}</span>
              <span class="scan-score-item s-chip" title="籌碼面">籌 ${c.chip_score}</span>
              <span class="scan-score-item s-val"  title="估值面">估 ${c.val_score}</span>
              <span class="scan-total">${c.total_score}<small>/100</small></span>
            </div>
          </div>
        </div>
        ${sigs ? `<div class="scan-signals">${sigs}</div>` : ''}
      </div>`;
  });

  list.innerHTML = rows.join('');
}


function renderHeatmaps(hm) {
  if (!hm) return;
  const asOf = el('heatmap-as-of');
  if (asOf && hm.as_of) {
    const hasTime = hm.as_of.includes(' ');
    asOf.textContent = (hasTime ? '資料時間：' : '資料日期：') + hm.as_of;
  }
  buildHeatmap('hm-twse-cap', hm.twse || [], 'cap', '上市市值');
  buildHeatmap('hm-twse-vol', hm.twse || [], 'vol', '上市成交額');
  buildHeatmap('hm-tpex-cap', hm.tpex || [], 'cap', '櫃買市值');
  buildHeatmap('hm-tpex-vol', hm.tpex || [], 'vol', '櫃買成交額');
}

function showLoading(show) {
  el('loadingOverlay').className = show ? 'loading-overlay' : 'loading-overlay hidden';
}

function showError(msg) {
  const existing = document.querySelector('.error-banner');
  if (existing) existing.remove();
  const div = document.createElement('div');
  div.className = 'error-banner';
  div.textContent = msg;
  document.querySelector('.main').prepend(div);
}

// Auto-refresh every 5 minutes
setInterval(loadData, 5 * 60 * 1000);

// VIX term-structure chart: re-render (no refetch) when a checkbox is toggled
const vixTermToggleEl = el('vixTermToggle');
if (vixTermToggleEl) {
  vixTermToggleEl.addEventListener('change', () => renderVixTermChart());
}

// Initial load
loadData();
