/**
 * GoldClaw Dashboard — Main Application Logic
 */

// === i18n ===
let lang = localStorage.getItem('goldclaw-lang') || 'zh';

const I18N = {
  zh: {
    // Header
    'btn.logs': '日志管理',
    'btn.config': '参数配置',
    'btn.backup': '数据备份',
    'btn.refresh': '刷新',
    'btn.lang': 'EN',
    'refreshed': '已刷新 ',
    // Tabs
    'tab.asset': '资产页',
    'tab.comm': '通讯状态',
    // Chart
    'chart.title': '金价记录折线图',
    'chart.loading': '加载中...',
    'chart.day': '日视图',
    'chart.week': '周视图',
    'chart.month': '月视图',
    'chart.records': '{count} 条记录',
    // Investors
    'inv.a.title': '投资者 A',
    'inv.a.subtitle': '趋势收割者 · CFD 1:20',
    'inv.b.title': '投资者 B',
    'inv.b.subtitle': '防御性狙击手 · CFD/SGLN',
    // Table headers
    'th.time': '时间',
    'th.assets': '资产',
    'th.decision': '决策',
    'th.size': '大小',
    'th.action': '操作',
    'no.trades': '暂无交易记录',
    // Comm
    'comm.title': '通讯状态监控',
    'comm.subtitle': 'GoldClaw ↔ OpenClaw 双向通讯',
    'comm.loading': '加载通讯日志...',
    'no.comm': '暂无通讯记录',
    'weekday': ['一', '二', '三', '四', '五', '六', '日'],
    // Config modal
    'config.title': '运行参数配置',
    'config.desc': '修改后立即持久化，下次 tick 自动生效。',
    'config.default': '默认 {val}',
    'config.reset': '恢复默认值',
    'btn.cancel': '取消',
    'btn.save': '保存',
    'btn.close': '关闭',
    'btn.confirmClear': '确认清除',
    'btn.backupNow': '立即备份',
    'btn.restore': '恢复',
    // Log modal
    'logs.title': '日志管理',
    'logs.selectTarget': '选择清除目标',
    'logs.priceTicks': 'price_ticks — 价格记录',
    'logs.commLog': 'comm_log — 通讯日志',
    'logs.retainRange': '保留范围',
    'logs.7days': '保留最近 7 天',
    'logs.30days': '保留最近 30 天',
    'logs.90days': '保留最近 90 天',
    'logs.all': '全部清除',
    // Backup modal
    'backup.title': '数据备份',
    'backup.desc': '备份目录: ~/GoldClaw/backup/ — 保留最近 10 份',
    'backup.noBackups': '暂无备份',
    // Alerts
    'alert.cleared': '已清除 {count} 条{type}',
    'alert.type.prices': '价格记录',
    'alert.type.comm': '通讯日志',
    'alert.clearFailed': '清除失败: ',
    'alert.invalidNum': '{label}: 请输入有效数字',
    'alert.configSaved': '已更新 {count} 项配置，下次 tick 自动生效',
    'alert.saveFailed': '保存失败: ',
    'alert.defaultsRestored': '已恢复全部默认值',
    'alert.restoreFailed': '恢复失败: ',
    'alert.backupOk': '备份成功',
    'alert.backupFailed': '备份失败: ',
    'alert.confirmRestore': '确认从 {file} 恢复数据库？当前数据将被覆盖。',
    'alert.restoreOk': '恢复成功，正在刷新...',
    'alert.loadFailed': '加载失败: ',
  },
  en: {
    'btn.logs': 'Logs',
    'btn.config': 'Settings',
    'btn.backup': 'Backup',
    'btn.refresh': 'Refresh',
    'btn.lang': '中',
    'refreshed': 'Refreshed ',
    'tab.asset': 'Assets',
    'tab.comm': 'Comm',
    'chart.title': 'Gold Price Chart',
    'chart.loading': 'Loading...',
    'chart.day': 'Day',
    'chart.week': 'Week',
    'chart.month': 'Month',
    'chart.records': '{count} records',
    'inv.a.title': 'Investor A',
    'inv.a.subtitle': 'Trend Harvester · CFD 1:20',
    'inv.b.title': 'Investor B',
    'inv.b.subtitle': 'Defensive Sniper · CFD/SGLN',
    'th.time': 'Time',
    'th.assets': 'Assets',
    'th.decision': 'Decision',
    'th.size': 'Size',
    'th.action': 'Action',
    'no.trades': 'No trades yet',
    'comm.title': 'Communication Monitor',
    'comm.subtitle': 'GoldClaw ↔ OpenClaw Bidirectional',
    'comm.loading': 'Loading comm logs...',
    'no.comm': 'No comm records',
    'weekday': ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    'config.title': 'Runtime Settings',
    'config.desc': 'Changes are saved instantly, effective on next tick.',
    'config.default': 'Default {val}',
    'config.reset': 'Reset Defaults',
    'btn.cancel': 'Cancel',
    'btn.save': 'Save',
    'btn.close': 'Close',
    'btn.confirmClear': 'Confirm Clear',
    'btn.backupNow': 'Backup Now',
    'btn.restore': 'Restore',
    'logs.title': 'Log Management',
    'logs.selectTarget': 'Select target',
    'logs.priceTicks': 'price_ticks — Price Records',
    'logs.commLog': 'comm_log — Comm Logs',
    'logs.retainRange': 'Retention',
    'logs.7days': 'Last 7 days',
    'logs.30days': 'Last 30 days',
    'logs.90days': 'Last 90 days',
    'logs.all': 'Clear all',
    'backup.title': 'Data Backup',
    'backup.desc': 'Backup dir: ~/GoldClaw/backup/ — Keep last 10',
    'backup.noBackups': 'No backups',
    'alert.cleared': 'Cleared {count} {type}',
    'alert.type.prices': 'price records',
    'alert.type.comm': 'comm logs',
    'alert.clearFailed': 'Clear failed: ',
    'alert.invalidNum': '{label}: enter a valid number',
    'alert.configSaved': 'Updated {count} settings, effective on next tick',
    'alert.saveFailed': 'Save failed: ',
    'alert.defaultsRestored': 'All defaults restored',
    'alert.restoreFailed': 'Restore failed: ',
    'alert.backupOk': 'Backup created',
    'alert.backupFailed': 'Backup failed: ',
    'alert.confirmRestore': 'Restore database from {file}? Current data will be overwritten.',
    'alert.restoreOk': 'Restored, refreshing...',
    'alert.loadFailed': 'Load failed: ',
  },
};

function t(key, vars) {
  let text = I18N[lang]?.[key] || I18N['zh']?.[key] || key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      text = text.replace(`{${k}}`, v);
    }
  }
  return text;
}

function toggleLang() {
  lang = lang === 'zh' ? 'en' : 'zh';
  localStorage.setItem('goldclaw-lang', lang);
  applyLang();
  refreshAll();
}

function applyLang() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    el.textContent = t(key);
  });
  document.querySelectorAll('[data-i18n-opt]').forEach(el => {
    const key = el.getAttribute('data-i18n-opt');
    el.textContent = t(key);
  });
  // Update chart subtitle if it has records text
  const subtitle = document.getElementById('chartSubtitle');
  if (subtitle && !subtitle.textContent.includes(t('chart.loading'))) {
    // keep the record count from last load
  }
  // Update lang toggle button
  const langBtn = document.getElementById('langToggle');
  if (langBtn) langBtn.textContent = t('btn.lang');
}

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
    subtitle.textContent = t('chart.records', { count: data.count });

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

      document.getElementById(`totalAssets${id}`).textContent = fmtUSD(inv.total_assets);

      const pnlEl = document.getElementById(`pnl${id}`);
      const pnlPct = inv.pnl_pct || 0;
      const pnlVal = inv.net_pnl || 0;
      pnlEl.textContent = `${pnlVal >= 0 ? '+' : ''}${fmtUSD2(pnlVal)} (${fmtPct(pnlPct)})`;
      pnlEl.className = pnlVal >= 0 ? 'pnl-positive' : 'pnl-negative';

      const badge = document.getElementById(`actionBadge${id}`);
      badge.textContent = actionLabel(inv.current_action);
      badge.className = `action-badge ${inv.current_action}`;

      const tpslEl = document.getElementById(`tpsl${id}`);
      if (tpslEl) {
        const tp = inv.tp && inv.tp > 0 ? fmtUSD2(inv.tp) : '--';
        const sl = inv.sl && inv.sl > 0 ? fmtUSD2(inv.sl) : '--';
        tpslEl.textContent = `TP:${tp}  SL:${sl}`;
      }
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
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--color-muted); padding:24px;">${t('no.trades')}</td></tr>`;
    } else {
      tbody.innerHTML = data.trades.map(tr => `
        <tr>
          <td class="time">${fmtDate(tr.timestamp)}<br>${fmtTime(tr.timestamp)}</td>
          <td>${fmtUSD(tr.total_assets_after)}</td>
          <td><span class="action-badge ${tr.action} btn-sm">${actionLabel(tr.action)}</span></td>
          <td>${tr.margin_committed ? fmtUSD(tr.margin_committed) : '--'}</td>
          <td>${tr.tp && tr.tp > 0 ? fmtUSD2(tr.tp) : '--'}</td>
          <td>${tr.sl && tr.sl > 0 ? fmtUSD2(tr.sl) : '--'}</td>
        </tr>
      `).join('');
    }

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
      container.innerHTML = `<div class="empty-state"><p>${t('no.comm')}</p></div>`;
      return;
    }

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
      container.innerHTML = `<div class="empty-state"><p>${t('no.comm')}</p></div>`;
      container.className = 'comm-grid';
      return;
    }

    if (view === 'week') {
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
      container.className = 'comm-grid month';

      const weekdayNames = t('weekday');
      let html = weekdayNames.map(d => `<div class="comm-grid-header">${d}</div>`).join('');

      const firstDay = new Date(days[0].day + 'T00:00:00Z');
      let startDow = firstDay.getUTCDay();
      startDow = startDow === 0 ? 6 : startDow - 1;
      for (let i = 0; i < startDow; i++) {
        html += `<div class="comm-grid-cell empty"></div>`;
      }

      for (const d of days) {
        const dayLabel = d.day.slice(8);
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
    const typeLabel = target === 'price_ticks' ? t('alert.type.prices') : t('alert.type.comm');
    alert(t('alert.cleared', { count: result.deleted, type: typeLabel }));
    closeLogModal();
    refreshAll();
  } catch (e) {
    alert(t('alert.clearFailed') + e.message);
  }
}

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
          <span class="config-default">${t('config.default', { val: cfg.default })}</span>
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
      alert(t('alert.invalidNum', { label: configData[key]?.label || key }));
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
    alert(t('alert.configSaved', { count: Object.keys(result.updated).length }));
  } catch (e) {
    alert(t('alert.saveFailed') + e.message);
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
  fetch(`${API}/config/reset`, { method: 'POST' })
    .then(() => alert(t('alert.defaultsRestored')))
    .catch(e => alert(t('alert.restoreFailed') + e.message));
}

document.getElementById('configModal').addEventListener('click', function(e) {
  if (e.target === this) closeConfigModal();
});

// === Backup Modal ===
async function openBackupModal() {
  document.getElementById('backupModal').classList.add('active');
  loadBackupList();
}

function closeBackupModal() {
  document.getElementById('backupModal').classList.remove('active');
}

async function loadBackupList() {
  const container = document.getElementById('backupList');
  try {
    const data = await fetchJSON(`${API}/backups`);
    if (data.backups.length === 0) {
      container.innerHTML = `<div style="text-align:center;color:var(--color-muted);padding:24px;">${t('backup.noBackups')}</div>`;
      return;
    }
    container.innerHTML = `<table class="data-table" style="font-size:13px;"><thead><tr><th>${t('th.time')}</th><th>${t('th.size')}</th><th>${t('th.action')}</th></tr></thead><tbody>` +
      data.backups.map(b => `
        <tr>
          <td>${b.time}</td>
          <td>${b.size_label}</td>
          <td><button class="btn btn-outline btn-sm" onclick="restoreBackup('${b.filename}')" style="font-size:11px;padding:2px 8px;">${t('btn.restore')}</button></td>
        </tr>
      `).join('') +
      '</tbody></table>';
  } catch (e) {
    container.innerHTML = `<div style="color:#e23b4a;padding:12px;">${t('alert.loadFailed')}${e.message}</div>`;
  }
}

async function createBackup() {
  try {
    const resp = await fetch(`${API}/backup`, { method: 'POST' });
    const result = await resp.json();
    if (result.ok) {
      alert(t('alert.backupOk'));
      loadBackupList();
    } else {
      alert(t('alert.backupFailed') + (result.detail || ''));
    }
  } catch (e) {
    alert(t('alert.backupFailed') + e.message);
  }
}

async function restoreBackup(filename) {
  if (!confirm(t('alert.confirmRestore', { file: filename }))) return;
  try {
    const resp = await fetch(`${API}/backup/restore`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename }),
    });
    const result = await resp.json();
    if (result.ok) {
      alert(t('alert.restoreOk'));
      refreshAll();
    } else {
      alert(t('alert.restoreFailed') + (result.detail || ''));
    }
  } catch (e) {
    alert(t('alert.restoreFailed') + e.message);
  }
}

document.getElementById('backupModal').addEventListener('click', function(e) {
  if (e.target === this) closeBackupModal();
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
  const now = new Date();
  const ts = now.getHours().toString().padStart(2,'0') + ':' + now.getMinutes().toString().padStart(2,'0') + ':' + now.getSeconds().toString().padStart(2,'0');
  const el = document.getElementById('lastRefresh');
  if (el) el.textContent = t('refreshed') + ts;
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
    if (state.priceChart) setTimeout(() => state.priceChart.resize(), 50);
  } else {
    document.getElementById('tabComm').classList.add('active');
  }
}

// === Init ===
document.addEventListener('DOMContentLoaded', () => {
  applyLang();
  refreshAll();
  startAutoRefresh(30000);
  initResizeHandles();

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) refreshAll();
  });
  window.addEventListener('focus', () => refreshAll());
});

// === Resize Handles ===
function initResizeHandles() {
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

      const ratio = dx / totalWidth;
      const delta = ratio * totalFlex;
      const newChartFlex = Math.max(1, currentChartFlex + delta);
      const newInvFlex = Math.max(0.5, totalFlex - newChartFlex);

      panelChart.style.flexGrow = newChartFlex;
      panelInvestors.style.flexGrow = newInvFlex;
    });

    handleH.addEventListener('dblclick', () => {
      panelChart.style.flexGrow = 3;
      panelInvestors.style.flexGrow = 2;
      if (state.priceChart) state.priceChart.resize();
    });
  }

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
      if (state.priceChart) state.priceChart.resize();
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  });
}
