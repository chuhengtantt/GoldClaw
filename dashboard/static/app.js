/**
 * GoldClaw Dashboard — Main Application Logic
 */

// === State ===
const state = {
  priceRange: 'day',
  pageA: 1,
  pageB: 1,
  pageComm: 1,
  pageSize: 20,
  commPageSize: 30,
  refreshInterval: null,
  priceChart: null,
};

// === API Helpers ===
const API = '/api';

async function fetchJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`API ${resp.status}: ${url}`);
  return resp.json();
}

// === Formatting ===
function fmtUSD(val) {
  if (val == null) return '--';
  return '$' + Number(val).toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function fmtUSD2(val) {
  if (val == null) return '--';
  return '$' + Number(val).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtPct(val) {
  if (val == null) return '--';
  const sign = val >= 0 ? '+' : '';
  return sign + (val * 100).toFixed(2) + '%';
}

function fmtTime(iso) {
  if (!iso) return '--';
  const d = new Date(iso);
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
}

function fmtDateTime(iso) {
  if (!iso) return '--';
  const d = new Date(iso);
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
}

function actionLabel(action) {
  const labels = {
    idle: 'IDLE', hold: 'HOLD', cfd_long: 'LONG', cfd_short: 'SHORT',
    sgln_long: 'SGLN', close: 'CLOSE',
  };
  return labels[action] || action;
}

// === Price Chart ===
async function loadPrices() {
  try {
    const data = await fetchJSON(`${API}/prices?range=${state.priceRange}`);
    const subtitle = document.getElementById('chartSubtitle');
    subtitle.textContent = `${data.count} 条记录`;

    const labels = data.data.map(d => fmtDateTime(d.time));
    const prices = data.data.map(d => d.price);

    if (state.priceChart) {
      state.priceChart.data.labels = labels;
      state.priceChart.data.datasets[0].data = prices;
      state.priceChart.update('none');
    } else {
      const ctx = document.getElementById('priceChart').getContext('2d');
      state.priceChart = new Chart(ctx, {
        type: 'line',
        data: {
          labels,
          datasets: [{
            label: 'XAU/USD',
            data: prices,
            borderColor: '#191c1f',
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 4,
            pointHoverBackgroundColor: '#191c1f',
            tension: 0.2,
            fill: false,
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: '#191c1f',
              titleFont: { family: 'Inter', size: 12 },
              bodyFont: { family: 'Inter', size: 13, weight: '600' },
              padding: 10,
              cornerRadius: 8,
              callbacks: {
                label: ctx => '$' + ctx.parsed.y.toLocaleString('en-US', { minimumFractionDigits: 2 }),
              },
            },
          },
          scales: {
            x: {
              display: true,
              grid: { display: false },
              ticks: { font: { family: 'Inter', size: 11 }, color: '#8d969e', maxTicksLimit: 8 },
            },
            y: {
              display: true,
              grid: { color: '#f4f4f4' },
              ticks: {
                font: { family: 'Inter', size: 11 },
                color: '#8d969e',
                callback: v => '$' + v.toLocaleString(),
              },
            },
          },
        },
      });
    }
  } catch (e) {
    console.error('Failed to load prices:', e);
  }
}

function switchRange(range, btn) {
  state.priceRange = range;
  document.querySelectorAll('.range-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  loadPrices();
}

// === Investors ===
async function loadInvestors() {
  try {
    const data = await fetchJSON(`${API}/investors`);
    for (const id of ['A', 'B']) {
      const inv = data.investors[id];
      if (!inv) continue;

      // Summary
      document.getElementById(`totalAssets${id}`).textContent = fmtUSD(inv.total_assets);

      const pnlEl = document.getElementById(`pnl${id}`);
      const pnlPct = inv.pnl_pct || 0;
      const pnlVal = inv.net_pnl || 0;
      pnlEl.textContent = `${pnlVal >= 0 ? '+' : ''}${fmtUSD2(pnlVal)} (${fmtPct(pnlPct)})`;
      pnlEl.className = pnlVal >= 0 ? 'pnl-positive' : 'pnl-negative';

      // Action badge
      const badge = document.getElementById(`actionBadge${id}`);
      badge.textContent = actionLabel(inv.current_action);
      badge.className = `action-badge ${inv.current_action}`;
    }
  } catch (e) {
    console.error('Failed to load investors:', e);
  }
}

// === Trade History Tables ===
async function loadTrades(investorId) {
  try {
    const page = investorId === 'A' ? state.pageA : state.pageB;
    const data = await fetchJSON(`${API}/investors/${investorId}/trades?page=${page}&size=${state.pageSize}`);

    const tbody = document.getElementById(`tradesBody${investorId}`);
    if (!data.trades || data.trades.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--color-muted); padding:24px;">暂无交易记录</td></tr>`;
    } else {
      tbody.innerHTML = data.trades.map(t => `
        <tr>
          <td class="time">${fmtTime(t.timestamp)}</td>
          <td>${fmtUSD(t.total_assets_after)}</td>
          <td><span class="action-badge ${t.action} btn-sm">${actionLabel(t.action)}</span></td>
          <td>${t.margin_committed ? fmtUSD(t.margin_committed) : '--'}</td>
          <td>${t.entry_price ? fmtUSD2(t.entry_price) : '--'}</td>
          <td>${t.exit_price ? fmtUSD2(t.exit_price) : '--'}</td>
        </tr>
      `).join('');
    }

    // Pagination
    const totalPages = data.total_pages || 1;
    const pageInfo = document.getElementById(`pageInfo${investorId}`);
    pageInfo.textContent = `${page}/${totalPages}`;
    pageInfo.dataset.total = totalPages;
  } catch (e) {
    console.error(`Failed to load trades for ${investorId}:`, e);
  }
}

function changePage(investorId, delta) {
  const pageInfo = document.getElementById(`pageInfo${investorId}`);
  const current = parseInt(pageInfo.textContent.split('/')[0]);
  const total = parseInt(pageInfo.dataset.total || '1');
  const newPage = Math.max(1, Math.min(total, current + delta));

  if (investorId === 'A') state.pageA = newPage;
  else state.pageB = newPage;

  loadTrades(investorId);
}

// === System State ===
async function loadSystem() {
  try {
    const data = await fetchJSON(`${API}/system`);
    const badge = document.getElementById('systemBadge');
    badge.textContent = data.state;
    badge.className = `system-badge ${data.state.toLowerCase()}`;

    document.getElementById('priceDisplay').textContent = `XAU ${fmtUSD2(data.gold_price)}`;
  } catch (e) {
    console.error('Failed to load system state:', e);
  }
}

// === Communication Panel ===
async function loadCommLog() {
  try {
    const data = await fetchJSON(`${API}/comm?page=${state.pageComm}&size=${state.commPageSize}`);
    const container = document.getElementById('commBody');

    if (!data.logs || data.logs.length === 0) {
      container.innerHTML = `<div class="empty-state"><p>暂无通讯记录</p></div>`;
      return;
    }

    // Build timeline rows
    const rows = data.logs.map(log => {
      const isGC = log.direction === 'goldclaw→openclaw' || log.direction === 'internal';
      const isOC = log.direction === 'openclaw→goldclaw';

      let arrow = '';
      if (log.direction === 'goldclaw→openclaw') arrow = '→';
      else if (log.direction === 'openclaw→goldclaw') arrow = '←';
      else arrow = '·';

      const dotClass = log.event_type || 'tick';
      const payload = JSON.parse(log.payload || '{}');

      let detail = '';
      if (log.event_type === 'tick') detail = `$${payload.price?.toFixed(2) || '--'}`;
      else if (log.event_type === 'state_change') detail = `${payload.from} → ${payload.to}`;
      else if (log.event_type === 'order') detail = `${payload.investor}: ${payload.action}`;
      else if (log.event_type === 'emergency') detail = payload.message || payload.event || '';
      else if (log.event_type === 'status_report') detail = `${payload.state} @ $${payload.price}`;

      const gcCell = isGC
        ? `<div class="comm-cell"><span class="time">${fmtTime(log.created_at)}</span><span class="comm-dot ${dotClass}"></span><div><div class="comm-event">${log.event_type}</div><div class="comm-detail">${detail}</div></div></div>`
        : `<div class="comm-cell"></div>`;

      const ocCell = isOC
        ? `<div class="comm-cell"><span class="time">${fmtTime(log.created_at)}</span><span class="comm-dot ${dotClass}"></span><div><div class="comm-event">${log.event_type}</div><div class="comm-detail">${detail}</div></div></div>`
        : `<div class="comm-cell"></div>`;

      const arrowClass = log.direction === 'goldclaw→openclaw' ? 'right' : (log.direction === 'openclaw→goldclaw' ? 'left' : '');

      return `
        <div class="comm-row">
          ${gcCell}
          <div class="comm-cell comm-arrow ${arrowClass}">${arrow}</div>
          ${ocCell}
        </div>
      `;
    }).join('');

    container.innerHTML = rows;

    // Pagination
    const totalPages = data.total_pages || 1;
    document.getElementById('pageInfoComm').textContent = `${state.pageComm}/${totalPages}`;
    document.getElementById('pageInfoComm').dataset.total = totalPages;
  } catch (e) {
    console.error('Failed to load comm log:', e);
  }
}

function changeCommPage(delta) {
  const pageInfo = document.getElementById('pageInfoComm');
  const total = parseInt(pageInfo.dataset.total || '1');
  state.pageComm = Math.max(1, Math.min(total, state.pageComm + delta));
  loadCommLog();
}

// === Log Management Modal ===
async function openLogModal() {
  document.getElementById('logModal').classList.add('active');
  try {
    const stats = await fetchJSON(`${API}/logs/stats`);
    document.getElementById('statPriceTicks').textContent = stats.price_ticks?.toLocaleString() || '0';
    document.getElementById('statCommLog').textContent = stats.comm_log?.toLocaleString() || '0';
    document.getElementById('statTradeHistory').textContent = stats.trade_history?.toLocaleString() || '0';
    document.getElementById('statViolations').textContent = stats.violations?.toLocaleString() || '0';
  } catch (e) {
    console.error('Failed to load log stats:', e);
  }
}

function closeLogModal() {
  document.getElementById('logModal').classList.remove('active');
}

async function clearLogs() {
  const target = document.getElementById('clearTarget').value;
  const days = parseInt(document.getElementById('clearRange').value);

  let before;
  if (days === 0) {
    before = new Date(Date.now() + 365 * 24 * 3600 * 1000).toISOString();
  } else {
    before = new Date(Date.now() - days * 24 * 3600 * 1000).toISOString();
  }

  try {
    const resp = await fetch(`${API}/logs/${target}?before=${encodeURIComponent(before)}`, { method: 'DELETE' });
    const result = await resp.json();
    alert(`已清除 ${result.deleted} 条${target === 'price_ticks' ? '价格记录' : '通讯日志'}`);
    closeLogModal();
    refreshAll();
  } catch (e) {
    alert('清除失败: ' + e.message);
  }
}

// Close modal on overlay click
document.getElementById('logModal').addEventListener('click', function(e) {
  if (e.target === this) closeLogModal();
});

// === Refresh ===
async function refreshAll() {
  await Promise.all([
    loadSystem(),
    loadPrices(),
    loadInvestors(),
    loadTrades('A'),
    loadTrades('B'),
    loadCommLog(),
  ]);
}

// === Auto Refresh ===
function startAutoRefresh(intervalMs = 30000) {
  if (state.refreshInterval) clearInterval(state.refreshInterval);
  state.refreshInterval = setInterval(refreshAll, intervalMs);
}

// === Init ===
document.addEventListener('DOMContentLoaded', () => {
  refreshAll();
  startAutoRefresh(30000);
});
