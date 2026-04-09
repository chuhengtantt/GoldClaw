/**
 * GoldClaw Dashboard — Main Application Logic
 */

// === State ===
const state = {
  priceRange: 'day',
  pageA: 1,
  pageB: 1,
  pageComm: 1,
  commView: 'day',
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

function fmtDate(iso) {
  if (!iso) return '--';
  const d = new Date(iso);
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
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
            borderColor: '#505a63',
            borderWidth: 2.5,
            pointRadius: 0,
            pointHoverRadius: 5,
            tension: 0.15,
            fill: false,
            spanGaps: false,
            segment: {
              borderColor: (ctx) => {
                const p0 = ctx.p0.parsed.y;
                const p1 = ctx.p1.parsed.y;
                if (p1 > p0) return '#e23b4a';
                if (p1 < p0) return '#00a87e';
                return '#505a63';
              },
            },
            pointHoverBackgroundColor: (ctx) => {
              const i = ctx.dataIndex;
              const data = ctx.dataset.data;
              if (i === 0) return '#505a63';
              return data[i] > data[i - 1] ? '#e23b4a' : '#00a87e';
            },
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
                label: function(ctx) {
                  const val = '$' + ctx.parsed.y.toLocaleString('en-US', { minimumFractionDigits: 2 });
                  const i = ctx.dataIndex;
                  const data = ctx.dataset.data;
                  if (i === 0) return val;
                  const diff = data[i] - data[i - 1];
                  const arrow = diff > 0 ? ' ↑' : diff < 0 ? ' ↓' : ' →';
                  return val + arrow;
                },
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
          <td class="time">${fmtDate(t.timestamp)}<br>${fmtTime(t.timestamp)}</td>
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
function switchCommView(view, btn) {
  state.commView = view;
  document.querySelectorAll('#commPanel .range-tab').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');

  const dayView = document.getElementById('commDayView');
  const gridView = document.getElementById('commGridView');
  const pagination = document.getElementById('paginationComm');

  if (view === 'day') {
    dayView.style.display = '';
    gridView.style.display = 'none';
    pagination.style.display = '';
    loadCommLog();
  } else {
    dayView.style.display = 'none';
    gridView.style.display = '';
    pagination.style.display = 'none';
    loadCommGrid(view);
  }
}

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

async function loadCommGrid(view) {
  try {
    const data = await fetchJSON(`${API}/comm/summary?range=${view}`);
    const container = document.getElementById('commGrid');
    const days = data.days || [];

    if (days.length === 0) {
      container.innerHTML = `<div class="empty-state"><p>暂无通讯记录</p></div>`;
      container.className = 'comm-grid';
      return;
    }

    if (view === 'week') {
      // Week view: 7 cells in one row
      container.className = 'comm-grid week';
      let html = days.map(d => {
        const dayLabel = d.day.slice(5);
        const total = d.gc_out + d.oc_in;
        return `
          <div class="comm-grid-cell${total ? '' : ' empty'}">
            <div class="cell-day">${dayLabel}</div>
            ${total ? `
              <div class="cell-counts">
                <span class="cell-gc" title="GC→OC">${d.gc_out}↑</span>
                <span class="cell-oc" title="OC→GC">${d.oc_in}↓</span>
              </div>
            ` : '<div class="cell-counts" style="color:var(--color-muted);font-size:11px;">--</div>'}
          </div>
        `;
      }).join('');
      container.innerHTML = html;
    } else {
      // Month view: calendar layout
      container.className = 'comm-grid month';

      // Weekday headers
      const weekdayNames = ['一', '二', '三', '四', '五', '六', '日'];
      let html = weekdayNames.map(d => `<div class="comm-grid-header">${d}</div>`).join('');

      // Calculate leading empty cells for first day of month
      const firstDay = new Date(days[0].day + 'T00:00:00Z');
      let startDow = firstDay.getUTCDay();
      startDow = startDow === 0 ? 6 : startDow - 1;
      for (let i = 0; i < startDow; i++) {
        html += `<div class="comm-grid-cell empty"></div>`;
      }

      // Day cells
      for (const d of days) {
        const dayLabel = d.day.slice(8); // DD
        const total = d.gc_out + d.oc_in;
        html += `
          <div class="comm-grid-cell${total ? '' : ' empty'}">
            <div class="cell-day">${dayLabel}</div>
            ${total ? `
              <div class="cell-counts">
                <span class="cell-gc" title="GC→OC">${d.gc_out}↑</span>
                <span class="cell-oc" title="OC→GC">${d.oc_in}↓</span>
              </div>
            ` : ''}
          </div>
        `;
      }

      container.innerHTML = html;
    }
  } catch (e) {
    console.error('Failed to load comm grid:', e);
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

// Config modal
let configData = {};

async function openConfigModal() {
  document.getElementById('configModal').classList.add('active');
  try {
    configData = await fetchJSON(`${API}/config`);
    const container = document.getElementById('configFields');
    container.innerHTML = Object.entries(configData).map(([key, cfg]) => `
      <div class="config-row">
        <label class="config-label">${cfg.label}</label>
        <div class="config-input-wrap">
          <input type="number" step="any" class="config-input" id="cfg_${key}" value="${cfg.value}" data-key="${key}">
          <span class="config-default">默认 ${cfg.default}</span>
        </div>
      </div>
    `).join('');
  } catch (e) {
    console.error('Failed to load config:', e);
  }
}

function closeConfigModal() {
  document.getElementById('configModal').classList.remove('active');
}

async function saveConfig() {
  const inputs = document.querySelectorAll('.config-input');
  const updates = {};
  for (const input of inputs) {
    const key = input.dataset.key;
    const val = parseFloat(input.value);
    if (isNaN(val)) {
      alert(`${configData[key]?.label || key}: 请输入有效数字`);
      return;
    }
    updates[key] = val;
  }
  try {
    const resp = await fetch(`${API}/config`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    });
    const result = await resp.json();
    closeConfigModal();
    alert(`已更新 ${Object.keys(result.updated).length} 项配置，下次 tick 自动生效`);
  } catch (e) {
    alert('保存失败: ' + e.message);
  }
}

function resetConfigDefaults() {
  const inputs = document.querySelectorAll('.config-input');
  for (const input of inputs) {
    const key = input.dataset.key;
    if (configData[key]) {
      input.value = configData[key].default;
    }
  }
  // 同时提交到后端
  const updates = {};
  for (const input of inputs) {
    updates[input.dataset.key] = parseFloat(input.value);
  }
  fetch(`${API}/config/reset`, { method: 'POST' })
    .then(() => alert('已恢复全部默认值'))
    .catch(e => alert('恢复失败: ' + e.message));
}

document.getElementById('configModal').addEventListener('click', function(e) {
  if (e.target === this) closeConfigModal();
});

// === Refresh ===
async function refreshAll() {
  await Promise.all([
    loadSystem(),
    loadPrices(),
    loadInvestors(),
    loadTrades('A'),
    loadTrades('B'),
    state.commView === 'day' ? loadCommLog() : loadCommGrid(state.commView),
  ]);
}

// === Auto Refresh ===
function startAutoRefresh(intervalMs = 30000) {
  if (state.refreshInterval) clearInterval(state.refreshInterval);
  state.refreshInterval = setInterval(refreshAll, intervalMs);
}

// === Tab Switching ===
function switchTab(tab, btn) {
  document.querySelectorAll('.tab-btn').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  if (tab === 'asset') {
    document.getElementById('tabAsset').classList.add('active');
    // Resize chart when switching back
    if (state.priceChart) setTimeout(() => state.priceChart.resize(), 50);
  } else {
    document.getElementById('tabComm').classList.add('active');
  }
}

// === Init ===
document.addEventListener('DOMContentLoaded', () => {
  refreshAll();
  startAutoRefresh(30000);
  initResizeHandles();
});

// === Resize Handles ===
function initResizeHandles() {
  // Horizontal handle: chart ↔ investors
  const topSection = document.getElementById('topSection');
  const panelChart = document.getElementById('panelChart');
  const panelInvestors = document.getElementById('panelInvestors');
  const handleH = document.getElementById('resizeHandle');

  if (handleH && topSection) {
    makeDraggable(handleH, (dx) => {
      const totalWidth = topSection.offsetWidth - handleH.offsetWidth;
      const currentChartFlex = parseFloat(panelChart.style.flexGrow) || 3;
      const currentInvFlex = parseFloat(panelInvestors.style.flexGrow) || 2;
      const totalFlex = currentChartFlex + currentInvFlex;

      // Convert dx to flex ratio change
      const ratio = dx / totalWidth;
      const delta = ratio * totalFlex;
      const newChartFlex = Math.max(1, currentChartFlex + delta);
      const newInvFlex = Math.max(0.5, totalFlex - newChartFlex);

      panelChart.style.flexGrow = newChartFlex;
      panelInvestors.style.flexGrow = newInvFlex;
    });

    // Double-click to reset
    handleH.addEventListener('dblclick', () => {
      panelChart.style.flexGrow = 3;
      panelInvestors.style.flexGrow = 2;
      if (state.priceChart) state.priceChart.resize();
    });
  }

  // Vertical handle: top section ↔ comm panel
  const commPanel = document.getElementById('commPanel');
  const handleV = document.getElementById('resizeHandleH');

  if (handleV && commPanel && topSection) {
    makeDraggable(handleV, (_dx, dy) => {
      const currentHeight = commPanel.offsetHeight;
      const newHeight = Math.max(160, currentHeight - dy);
      commPanel.style.maxHeight = newHeight + 'px';
      topSection.style.flex = `1 1 calc(100% - ${newHeight + 24}px)`;
    });

    handleV.addEventListener('dblclick', () => {
      commPanel.style.maxHeight = '';
      topSection.style.flex = '';
    });
  }

  // Investor A ↔ B handle
  const panelInvA = document.getElementById('panelInvA');
  const panelInvB = document.getElementById('panelInvB');
  const handleInv = document.getElementById('resizeHandleInv');

  if (handleInv && panelInvA && panelInvB) {
    makeDraggable(handleInv, (_dx, dy) => {
      const currentA = panelInvA.offsetHeight;
      const newA = Math.max(100, currentA + dy);
      panelInvA.style.flex = `0 0 ${newA}px`;
      panelInvB.style.flex = '1 1 0';
    });

    handleInv.addEventListener('dblclick', () => {
      panelInvA.style.flex = '';
      panelInvB.style.flex = '';
    });
  }
}

function makeDraggable(handle, onMove) {
  let startX, startY;

  handle.addEventListener('mousedown', (e) => {
    e.preventDefault();
    startX = e.clientX;
    startY = e.clientY;
    handle.classList.add('active');
    document.body.style.cursor = getComputedStyle(handle).cursor;
    document.body.style.userSelect = 'none';

    const onMouseMove = (e) => {
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      startX = e.clientX;
      startY = e.clientY;
      onMove(dx, dy);
    };

    const onMouseUp = () => {
      handle.classList.remove('active');
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      // Resize chart after drag
      if (state.priceChart) state.priceChart.resize();
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  });
}
