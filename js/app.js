/* Taiwan Market Dashboard - Main Application */
'use strict';

const DATA_URL = 'data/market_data.json';
let institutionalChart = null;
let vixtwChart = null;
let vixUsChart = null;

// ─── Chart.js global defaults ───────────────────────────────────────────────
Chart.defaults.color = '#8fa3bf';
Chart.defaults.borderColor = '#1e2d45';
Chart.defaults.font.family = "'Segoe UI', 'PingFang TC', 'Microsoft JhengHei', sans-serif";

// ─── Entry point ─────────────────────────────────────────────────────────────
async function loadData() {
  showLoading(true);
  try {
    const res = await fetch(`${DATA_URL}?_=${Date.now()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    render(data);
  } catch (err) {
    console.error('Failed to load data:', err);
    showError('無法載入市場數據。請確認 GitHub Actions 已執行並生成 data/market_data.json。\n' + err.message);
  } finally {
    showLoading(false);
  }
}

function render(data) {
  updateHeader(data);
  updateKeyIndicators(data);
  renderUsIndices(data.vix);
  updateSignalBanner(data.signal);
  renderTermStructure(data.vix);
  renderGauge(data.cnn_fear_greed);
  renderInstitutionalChart(data.institutional);
  renderVixCharts(data.vix_history);
  renderSignalTable(data.signal);
  renderAnalysis(data.analysis, data.last_updated);
  renderInstitutionalBreakdown(data.institutional);
}

// ─── Header ──────────────────────────────────────────────────────────────────
function updateHeader(data) {
  const dt = new Date(data.last_updated || data.last_updated_utc);
  el('lastUpdated').textContent = isNaN(dt) ? '—' : dt.toLocaleString('zh-TW');

  // Market status heuristic (Taiwan market 09:00–13:30 TST Mon–Fri)
  const now = new Date();
  const tst = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Taipei' }));
  const day = tst.getDay(); // 0=Sun, 6=Sat
  const hour = tst.getHours(), min = tst.getMinutes();
  const timeNum = hour * 100 + min;
  const isOpen = day >= 1 && day <= 5 && timeNum >= 900 && timeNum < 1330;

  const dot = el('statusDot');
  dot.className = `status-dot ${isOpen ? 'open' : 'closed'}`;
  el('statusText').textContent = isOpen ? '台灣市場交易中' : '市場休市';
}

// ─── Key Indicators ───────────────────────────────────────────────────────────
function updateKeyIndicators(data) {
  const vix = data.vix || {};
  const cnn = data.cnn_fear_greed || {};
  const inst = data.institutional || {};

  // TWII
  updatePriceCard('twii', vix.twii, '', '點');

  // TPEX 櫃買指數
  updatePriceCard('tpex', vix.tpex, '', '點');

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
    { id: 'sp500',  key: 'sp500',  suffix: '' },
    { id: 'nasdaq', key: 'nasdaq', suffix: '' },
    { id: 'dji',    key: 'dji',    suffix: '' },
  ].forEach(({ id, key, suffix }) => {
    const t = vix[key];
    if (!t || t.current == null) return;
    updatePriceCard(id, t, '', suffix);
    const badge = el(`${id}-badge`);
    if (badge && t.change_pct != null) {
      const up = t.change_pct > 0;
      badge.textContent = (up ? '▲ ' : '▼ ') + Math.abs(t.change_pct).toFixed(2) + '%';
      badge.className = `card-badge ${up ? 'badge--bull' : 'badge--bear'}`;
    }
  });
}

function updatePriceCard(id, ticker, prefix, suffix) {
  if (!ticker) return;
  const val = ticker.current;
  if (val == null) { el(`${id}-value`).textContent = 'N/A'; return; }

  el(`${id}-value`).textContent = prefix + fmtNum(val) + suffix;

  if (ticker.change != null) {
    const sign = ticker.change >= 0 ? '+' : '';
    const cls = ticker.change > 0 ? 'change-up' : ticker.change < 0 ? 'change-down' : 'change-flat';
    el(`${id}-change`).textContent = `${sign}${ticker.change.toFixed(2)} (${sign}${ticker.change_pct?.toFixed(2)}%)`;
    el(`${id}-change`).className = `card-change ${cls}`;
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

  renderLineChart('vixUsChart', vixUsChart, history.vix, '美股VIX', '#ff9800', [15, 20, 30]);
  vixUsChart = lastChart;
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
    const barColor = s > 0 ? '#00e676' : s < 0 ? '#f44336' : '#ffc107';
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

// Initial load
loadData();
