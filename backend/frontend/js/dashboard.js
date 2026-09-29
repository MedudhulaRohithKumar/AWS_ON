/**
 * CSR Dashboard — User View
 * Loads servers, extensions, and personal activity. Handles extend/stop modals.
 */
import {
  requireAuth, logout, api, showToast, showConfirm,
  formatDate, timeUntil, statusBadge, typeBadge,
  isAdmin, initUserDisplay, getUser,
} from './api.js';

if (!requireAuth()) throw new Error('Not authenticated');
initUserDisplay();

// ─── Elements ──────────────────────────────────────────────────

const serversGrid    = document.getElementById('serversGrid');
const statTotal      = document.getElementById('statTotal');
const statRunning    = document.getElementById('statRunning');
const statMyExt      = document.getElementById('statMyExt');
const activeExtBanner= document.getElementById('activeExtBanner');
const activeExtList  = document.getElementById('activeExtList');
const activityBody   = document.getElementById('activityBody');
const extendModal    = document.getElementById('extendModal');
const refreshBtn     = document.getElementById('refreshBtn');
const logoutBtn      = document.getElementById('logoutBtn');

// Extend modal elements
let currentServerId = null;

// ─── Load everything ───────────────────────────────────────────

async function loadAll() {
  await Promise.all([loadServers(), loadActivity()]);
}

async function loadServers() {
  try {
    const [servers, myExtensions] = await Promise.all([
      api.get('/api/servers'),
      api.get('/api/extensions/mine'),
    ]);

    const myActiveExt = myExtensions.filter(e => e.status === 'active');

    // Stats
    statTotal.textContent   = servers.length;
    statRunning.textContent = servers.filter(s => s.status === 'running' || s.status === 'available').length;
    statMyExt.textContent   = myActiveExt.length;

    // Active extensions banner
    if (myActiveExt.length > 0) {
      activeExtBanner.classList.remove('hidden');
      activeExtList.innerHTML = myActiveExt.map(ext => `
        <div style="display:flex;align-items:center;gap:12px;padding:8px 12px;
                    background:var(--bg-primary);border-radius:var(--radius-sm);
                    font-size:0.85rem;">
          <span style="color:var(--success);">🛡</span>
          <strong style="color:var(--text-primary);">${ext.display_name}</strong>
          <span class="mono" style="color:var(--text-muted);">${ext.instance_id}</span>
          <span style="color:var(--success);margin-left:auto;">${timeUntil(ext.extended_until)}</span>
          <span style="color:var(--text-muted);font-size:0.78rem;">Until ${formatDate(ext.extended_until)}</span>
        </div>
      `).join('');
    } else {
      activeExtBanner.classList.add('hidden');
    }

    // Build extension map for quick lookup
    const extMap = {};
    myActiveExt.forEach(e => { extMap[e.instance_id] = e; });

    // Server cards
    if (servers.length === 0) {
      serversGrid.innerHTML = `
        <div class="empty-state" style="grid-column:1/-1;">
          <div class="empty-state-icon">🖥</div>
          <div class="empty-state-title">No servers registered</div>
          <p class="empty-state-desc">Ask your CSR admin to add servers to the portal.</p>
        </div>`;
      return;
    }

    serversGrid.innerHTML = servers.map(server => {
      const ext = extMap[server.instance_id];
      const isExtended = !!ext;
      const isEC2 = server.type === 'EC2';
      const isRunning = server.status === 'running' || server.status === 'available';

      return `
        <div class="server-card ${isExtended ? 'extended' : ''} fade-in" id="card-${server.id}">
          <div class="server-card-header">
            <div class="server-icon ${isEC2 ? 'ec2' : 'rds'}">
              ${isEC2 ? '🖥' : '🗄'}
            </div>
            <div style="flex:1;min-width:0;margin-left:14px;">
              <div class="server-name truncate" title="${server.display_name}">${server.display_name}</div>
              <div class="server-id-badge mono">${server.instance_id}</div>
            </div>
            ${statusBadge(server.status)}
          </div>

          <div class="server-meta-tags">
            ${typeBadge(server.type)}
            <span class="badge badge-muted">📍 ${server.region}</span>
          </div>

          ${isExtended ? `
            <div class="server-extension-banner">
              <div style="display:flex;align-items:center;gap:6px;font-weight:600;color:var(--success);">
                <span>🛡</span>
                <span>Protected until ${formatDate(ext.extended_until)}</span>
              </div>
              <div style="font-size:0.78rem;color:var(--text-secondary);margin-top:3px;">
                ⏳ ${timeUntil(ext.extended_until)}
              </div>
            </div>
          ` : ''}

          <div class="server-card-actions">
            <button
              class="btn ${isRunning ? 'btn-primary' : 'btn-success'} btn-sm"
              style="flex: 1; justify-content: center; padding: 10px 14px;"
              onclick="openExtend('${server.id}', '${server.display_name}', '${server.instance_id}')">
              ${isRunning ? '⏰ Extend' : '⚡ Start & Extend'}
            </button>
            ${isRunning ? `
              <button
                class="btn btn-danger btn-sm"
                style="justify-content: center; padding: 10px 14px;"
                onclick="stopServer('${server.id}', '${server.display_name}')">
                ⏹ Stop
              </button>` : ''}
          </div>
        </div>`;
    }).join('');

  } catch (err) {
    showToast(err.message, 'error');
    serversGrid.innerHTML = `<div class="empty-state" style="grid-column:1/-1;"><div class="empty-state-icon">⚠️</div><p class="empty-state-desc">${err.message}</p></div>`;
  }
}

async function loadActivity() {
  try {
    const user = getUser();
    const activity = await api.get('/api/extensions/mine');

    // Show full activity from the admin endpoint if possible
    let rows = [];
    try {
      const allActivity = await api.get('/api/activity').catch(() => null);
      if (allActivity) {
        rows = allActivity.filter(a => a.user_id === user?.id).slice(0, 20);
      }
    } catch { /* user may not have access */ }

    // Fallback to extensions as activity
    if (!rows.length) {
      rows = activity.slice(0, 20).map(e => ({
        action: e.status === 'active' ? 'EXTEND_INSTANCE' : e.status.toUpperCase(),
        resource_id: e.instance_id,
        resource_type: e.instance_type,
        details: `Extended ${e.display_name} until ${formatDate(e.extended_until)}`,
        timestamp: e.requested_at,
        ip_address: '—',
      }));
    }

    if (!rows.length) {
      activityBody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:32px;color:var(--text-muted);">No activity yet</td></tr>`;
      return;
    }

    const actionColors = {
      LOGIN: 'badge-info', LOGOUT: 'badge-muted',
      EXTEND_INSTANCE: 'badge-success', STOP_INSTANCE: 'badge-danger',
      FAILED_LOGIN: 'badge-danger',
    };

    activityBody.innerHTML = rows.map(a => `
      <tr>
        <td><span class="badge ${actionColors[a.action] || 'badge-muted'}" style="font-size:0.7rem;">${a.action}</span></td>
        <td class="mono" style="font-size:0.8rem;">${a.resource_id || '—'}</td>
        <td style="font-size:0.82rem;color:var(--text-secondary);">${a.details || '—'}</td>
        <td style="font-size:0.82rem;white-space:nowrap;">${formatDate(a.timestamp)}</td>
        <td class="mono" style="font-size:0.78rem;color:var(--text-muted);">${a.ip_address || '—'}</td>
      </tr>`).join('');

  } catch (err) {
    activityBody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-muted);">${err.message}</td></tr>`;
  }
}

// ─── Extend Modal ──────────────────────────────────────────────

window.openExtend = function(serverId, name, instanceId) {
  currentServerId = serverId;
  document.getElementById('extendServerName').textContent = name;
  document.getElementById('extendServerId').textContent  = instanceId;
  document.getElementById('extendError').style.display = 'none';
  document.getElementById('extendPreview').style.display = 'none';

  // Default: today at 9 PM IST
  const now = new Date();
  const todayIST = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
  todayIST.setHours(21, 0, 0, 0);

  const yyyy = todayIST.getFullYear();
  const mm   = String(todayIST.getMonth() + 1).padStart(2, '0');
  const dd   = String(todayIST.getDate()).padStart(2, '0');
  document.getElementById('extendDate').value = `${yyyy}-${mm}-${dd}`;
  document.getElementById('extendTime').value = '21:00';

  updatePreview();
  extendModal.classList.add('active');
};

function updatePreview() {
  const date = document.getElementById('extendDate').value;
  const time = document.getElementById('extendTime').value;
  const preview = document.getElementById('extendPreview');
  if (!date || !time) return;

  // Interpret as IST (UTC+5:30)
  const [y, mo, d]  = date.split('-').map(Number);
  const [h, min]    = time.split(':').map(Number);
  const istDate = new Date(Date.UTC(y, mo - 1, d, h - 5, min - 30));
  const utcStr = istDate.toISOString().replace('.000Z', 'Z');

  const diff = istDate - Date.now();
  if (diff <= 0) {
    preview.style.display = 'block';
    preview.className = 'docs-callout warning';
    preview.innerHTML = '⚠️ Selected time is in the past. Please choose a future time.';
    return;
  }

  const hh = Math.floor(diff / 3600000);
  const mm2 = Math.floor((diff % 3600000) / 60000);
  preview.style.display = 'block';
  preview.className = 'docs-callout';
  preview.innerHTML = `
    ⚡ Server will run for <strong>${hh}h ${mm2}m</strong> from now.<br/>
    <span style="font-size:0.78rem;opacity:0.8;">UTC: ${utcStr}</span>`;
}

document.getElementById('extendDate').addEventListener('change', updatePreview);
document.getElementById('extendTime').addEventListener('change', updatePreview);

document.getElementById('closeExtendModal').addEventListener('click', () => extendModal.classList.remove('active'));
document.getElementById('cancelExtendBtn').addEventListener('click', () => extendModal.classList.remove('active'));
extendModal.addEventListener('click', e => { if (e.target === extendModal) extendModal.classList.remove('active'); });

document.getElementById('confirmExtendBtn').addEventListener('click', async () => {
  const date = document.getElementById('extendDate').value;
  const time = document.getElementById('extendTime').value;
  const errEl = document.getElementById('extendError');
  const btnText = document.getElementById('extendBtnText');
  const spinner = document.getElementById('extendSpinner');
  const confirmBtn = document.getElementById('confirmExtendBtn');

  errEl.style.display = 'none';
  if (!date || !time) { errEl.textContent = 'Please select a date and time.'; errEl.style.display = 'block'; return; }

  // Convert IST → UTC
  const [y, mo, d] = date.split('-').map(Number);
  const [h, min]   = time.split(':').map(Number);
  const istDate = new Date(Date.UTC(y, mo - 1, d, h - 5, min - 30));

  if (istDate <= new Date()) {
    errEl.textContent = 'Please choose a future time.';
    errEl.style.display = 'block';
    return;
  }

  confirmBtn.disabled = true;
  btnText.textContent = 'Processing…';
  spinner.classList.remove('hidden');

  try {
    await api.post(`/api/servers/${currentServerId}/extend`, {
      extended_until: istDate.toISOString(),
    });
    extendModal.classList.remove('active');
    showToast(`Server extended until ${date} ${time} IST ✅`, 'success');
    await loadAll();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.style.display = 'block';
  } finally {
    confirmBtn.disabled = false;
    btnText.textContent = '⚡ Extend Now';
    spinner.classList.add('hidden');
  }
});

// ─── Stop Server ───────────────────────────────────────────────

window.stopServer = async function(serverId, name) {
  const confirmed = await showConfirm({
    title: 'Stop Instance',
    message: `Are you sure you want to stop "${name}" now? This will immediately remove CSR protection and stop the instance.`,
    confirmText: 'Stop Instance',
    type: 'danger',
    icon: '⏹'
  });
  if (!confirmed) return;
  try {
    await api.post(`/api/servers/${serverId}/stop`);
    showToast(`${name} stopped successfully`, 'success');
    await loadAll();
  } catch (err) {
    showToast(err.message, 'error');
  }
};

// ─── Buttons ───────────────────────────────────────────────────

refreshBtn.addEventListener('click', async () => {
  refreshBtn.disabled = true;
  refreshBtn.textContent = '⏳ Refreshing…';
  await loadAll();
  refreshBtn.disabled = false;
  refreshBtn.textContent = '🔄 Refresh';
});

logoutBtn.addEventListener('click', async () => {
  const confirmed = await showConfirm({
    title: 'Sign Out',
    message: 'Are you sure you want to sign out of CSR?',
    confirmText: 'Sign Out',
    cancelText: 'Stay Logged In',
    type: 'danger',
    icon: '🚪'
  });
  if (confirmed) logout();
});

// Admin redirect
if (isAdmin()) {
  const adminLink = document.createElement('a');
  adminLink.href = 'admin.html';
  adminLink.className = 'sidebar-item';
  adminLink.innerHTML = `<svg class="item-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>Admin Panel`;
  document.querySelector('.sidebar-nav').appendChild(adminLink);
}

// ─── Init ──────────────────────────────────────────────────────

loadAll();
// Auto-refresh every 60 seconds
setInterval(loadAll, 60000);
