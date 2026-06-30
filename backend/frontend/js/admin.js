/**
 * CSR Admin Panel Logic
 * Handles all 5 tabs: Users, Servers, Activity, Reports, Leaderboard
 */
import {
  requireAdmin, logout, api, showToast,
  formatDate, statusBadge, typeBadge, initUserDisplay,
} from './api.js';

if (!requireAdmin()) throw new Error('Not authenticated or not admin');
initUserDisplay();

// ─── Tab Navigation ────────────────────────────────────────────

const sidebarItems = document.querySelectorAll('.sidebar-item[data-tab]');
const tabPanels    = document.querySelectorAll('.tab-panel');

function switchTab(tab) {
  sidebarItems.forEach(i => i.classList.toggle('active', i.dataset.tab === tab));
  tabPanels.forEach(p => p.classList.toggle('active', p.id === `tab-${tab}`));
  loadTab(tab);
}

sidebarItems.forEach(item => {
  item.addEventListener('click', () => switchTab(item.dataset.tab));
});

// Close any modal with data-close
document.querySelectorAll('[data-close]').forEach(btn => {
  btn.addEventListener('click', () => {
    document.getElementById(btn.dataset.close).classList.remove('active');
  });
});
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', e => {
    if (e.target === overlay) overlay.classList.remove('active');
  });
});

// ─── Load Tab Content ──────────────────────────────────────────

const loaded = new Set();

function loadTab(tab) {
  const loaders = {
    users: loadUsers,
    servers: loadServers,
    activity: loadActivity,
    reports: loadReports,
    leaderboard: loadLeaderboard,
  };
  loaders[tab]?.();
}

// ─── USERS TAB ─────────────────────────────────────────────────

async function loadUsers() {
  const tbody = document.getElementById('usersBody');
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-muted);">Loading…</td></tr>';
  try {
    const users = await api.get('/api/admin/users');
    if (!users.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:32px;color:var(--text-muted);">No users found</td></tr>';
      return;
    }
    tbody.innerHTML = users.map(u => `
      <tr>
        <td>
          <div style="display:flex;align-items:center;gap:10px;">
            <div class="user-avatar" style="width:28px;height:28px;font-size:0.7rem;">${u.username.slice(0,2).toUpperCase()}</div>
            <strong style="font-size:0.875rem;">${u.username}</strong>
          </div>
        </td>
        <td style="color:var(--text-secondary);font-size:0.875rem;">${u.email}</td>
        <td>${u.role === 'admin'
          ? '<span class="badge badge-orange">Admin</span>'
          : '<span class="badge badge-muted">User</span>'}</td>
        <td>${u.is_active
          ? '<span class="badge badge-success">Active</span>'
          : '<span class="badge badge-danger">Inactive</span>'}</td>
        <td style="font-size:0.82rem;color:var(--text-muted);">${formatDate(u.created_at)}</td>
        <td>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-ghost btn-sm" onclick='openEditUser(${JSON.stringify(u)})'>✏️ Edit</button>
            ${u.is_active ? `<button class="btn btn-danger btn-sm" onclick="deactivateUser('${u.id}','${u.username}')">⛔ Disable</button>` : ''}
          </div>
        </td>
      </tr>`).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--danger);">${err.message}</td></tr>`;
  }
}

let availableServersCache = null;

async function loadServersForModal(containerId, selectedServers = []) {
  const container = document.getElementById(containerId);
  container.innerHTML = '<span style="color:var(--text-muted);font-size:0.8rem;">Loading...</span>';
  try {
    if (!availableServersCache) {
      availableServersCache = await api.get('/api/servers');
    }
    if (!availableServersCache.length) {
      container.innerHTML = '<span style="color:var(--text-muted);font-size:0.8rem;">No servers available.</span>';
      return;
    }
    
    container.innerHTML = availableServersCache.map(s => `
      <label style="display:flex; align-items:center; gap:8px; margin-bottom:4px; font-size:0.875rem; cursor:pointer;">
        <input type="checkbox" name="assign_server" value="${s.instance_id}" ${selectedServers.includes(s.instance_id) ? 'checked' : ''} />
        ${s.display_name} <span class="mono" style="color:var(--text-muted); font-size:0.75rem;">(${s.instance_id})</span>
      </label>
    `).join('');
  } catch (err) {
    container.innerHTML = `<span style="color:var(--danger);font-size:0.8rem;">${err.message}</span>`;
  }
}

// Add User
document.getElementById('openAddUserBtn').addEventListener('click', () => {
  ['newUsername','newEmail','newPassword'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('newRole').value = 'user';
  document.getElementById('addUserError').style.display = 'none';
  loadServersForModal('newServersList', []);
  document.getElementById('addUserModal').classList.add('active');
});

document.getElementById('confirmAddUserBtn').addEventListener('click', async () => {
  const btn = document.getElementById('confirmAddUserBtn');
  const errEl = document.getElementById('addUserError');
  errEl.style.display = 'none';

  const assigned = Array.from(document.querySelectorAll('#newServersList input[name="assign_server"]:checked')).map(cb => cb.value);

  const body = {
    username: document.getElementById('newUsername').value.trim(),
    email:    document.getElementById('newEmail').value.trim(),
    password: document.getElementById('newPassword').value,
    role:     document.getElementById('newRole').value,
    assigned_servers: assigned,
  };

  if (!body.username || !body.email || !body.password) {
    errEl.textContent = 'All fields are required.'; errEl.style.display = 'block'; return;
  }
  if (body.password.length < 8) {
    errEl.textContent = 'Password must be at least 8 characters.'; errEl.style.display = 'block'; return;
  }

  btn.disabled = true; btn.textContent = 'Creating…';
  try {
    await api.post('/api/admin/users', body);
    document.getElementById('addUserModal').classList.remove('active');
    showToast(`User '${body.username}' created successfully`, 'success');
    loadUsers();
  } catch (err) {
    errEl.textContent = err.message; errEl.style.display = 'block';
  } finally {
    btn.disabled = false; btn.textContent = 'Create User';
  }
});

// Edit User
window.openEditUser = function(user) {
  document.getElementById('editUserId').value   = user.id;
  document.getElementById('editEmail').value    = user.email;
  document.getElementById('editRole').value     = user.role;
  document.getElementById('editActive').value   = String(user.is_active);
  document.getElementById('editPassword').value = '';
  document.getElementById('editUserError').style.display = 'none';
  loadServersForModal('editServersList', user.assigned_servers || []);
  document.getElementById('editUserModal').classList.add('active');
};

document.getElementById('confirmEditUserBtn').addEventListener('click', async () => {
  const btn = document.getElementById('confirmEditUserBtn');
  const errEl = document.getElementById('editUserError');
  errEl.style.display = 'none';

  const userId = document.getElementById('editUserId').value;
  const assigned = Array.from(document.querySelectorAll('#editServersList input[name="assign_server"]:checked')).map(cb => cb.value);

  const body = {
    email:     document.getElementById('editEmail').value.trim() || undefined,
    role:      document.getElementById('editRole').value,
    is_active: document.getElementById('editActive').value === 'true',
    assigned_servers: assigned,
  };
  const pwd = document.getElementById('editPassword').value;
  if (pwd) body.password = pwd;

  btn.disabled = true; btn.textContent = 'Saving…';
  try {
    await api.put(`/api/admin/users/${userId}`, body);
    document.getElementById('editUserModal').classList.remove('active');
    showToast('User updated', 'success');
    loadUsers();
  } catch (err) {
    errEl.textContent = err.message; errEl.style.display = 'block';
  } finally {
    btn.disabled = false; btn.textContent = 'Save Changes';
  }
});

window.deactivateUser = async function(userId, username) {
  if (!confirm(`Deactivate user '${username}'? They will no longer be able to log in.`)) return;
  try {
    await api.delete(`/api/admin/users/${userId}`);
    showToast(`User '${username}' deactivated`, 'success');
    loadUsers();
  } catch (err) {
    showToast(err.message, 'error');
  }
};

// ─── SERVERS TAB ────────────────────────────────────────────────

async function loadServers() {
  const ec2Tbody = document.getElementById('ec2ServersBody');
  const rdsTbody = document.getElementById('rdsServersBody');
  ec2Tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-muted);">Loading…</td></tr>';
  rdsTbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-muted);">Loading…</td></tr>';
  try {
    const servers = await api.get('/api/servers');
    const ec2Servers = servers.filter(s => s.type === 'EC2');
    const rdsServers = servers.filter(s => s.type === 'RDS');

    if (!ec2Servers.length) {
      ec2Tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:32px;color:var(--text-muted);">No EC2 servers registered.</td></tr>';
    } else {
      ec2Tbody.innerHTML = ec2Servers.map(s => `
        <tr>
          <td><strong style="font-size:0.875rem;">${s.display_name}</strong></td>
          <td class="mono" style="font-size:0.8rem;color:var(--text-muted);">${s.instance_id}</td>
          <td style="font-size:0.82rem;">${s.region}</td>
          <td style="font-size:0.82rem;color:var(--text-secondary);">${s.added_by || '—'}</td>
          <td>${statusBadge(s.status)}</td>
          <td>
            <button class="btn btn-danger btn-sm" onclick="removeServer('${s.id}','${s.display_name}')">🗑 Remove</button>
          </td>
        </tr>`).join('');
    }

    if (!rdsServers.length) {
      rdsTbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:32px;color:var(--text-muted);">No RDS databases registered.</td></tr>';
    } else {
      rdsTbody.innerHTML = rdsServers.map(s => `
        <tr>
          <td><strong style="font-size:0.875rem;">${s.display_name}</strong></td>
          <td class="mono" style="font-size:0.8rem;color:var(--text-muted);">${s.instance_id}</td>
          <td style="font-size:0.82rem;">${s.region}</td>
          <td style="font-size:0.82rem;color:var(--text-secondary);">${s.added_by || '—'}</td>
          <td>${statusBadge(s.status)}</td>
          <td>
            <button class="btn btn-danger btn-sm" onclick="removeServer('${s.id}','${s.display_name}')">🗑 Remove</button>
          </td>
        </tr>`).join('');
    }
  } catch (err) {
    ec2Tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--danger);">${err.message}</td></tr>`;
    rdsTbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--danger);">${err.message}</td></tr>`;
  }
}

// Discover
document.getElementById('discoverBtn').addEventListener('click', async () => {
  const btn = document.getElementById('discoverBtn');
  const resultsDiv = document.getElementById('discoverResults');
  btn.disabled = true; btn.textContent = '🔍 Scanning…';
  try {
    const { instances } = await api.get('/api/servers/discover');
    if (!instances.length) {
      resultsDiv.classList.remove('hidden');
      resultsDiv.innerHTML = `<div class="card"><p style="text-align:center;padding:20px;color:var(--text-muted);">No EC2 instances found with tag TURN_UP=UAT_EXTEND in ap-south-1.</p></div>`;
    } else {
      resultsDiv.classList.remove('hidden');
      resultsDiv.innerHTML = `
        <div class="card">
          <div class="card-header"><div class="card-title">🔍 Discovered Instances (${instances.length})</div></div>
          <div style="display:flex;flex-direction:column;gap:8px;">
            ${instances.map(i => `
              <div style="display:flex;align-items:center;gap:12px;padding:10px 12px;
                          background:var(--bg-primary);border-radius:var(--radius-sm);">
                <span>🖥</span>
                <strong style="font-size:0.875rem;">${i.display_name}</strong>
                <span class="mono" style="font-size:0.8rem;color:var(--text-muted);">${i.instance_id}</span>
                ${statusBadge(i.state)}
                <div style="margin-left:auto;">
                  ${i.already_added
                    ? '<span class="badge badge-muted">Already Added</span>'
                    : `<button class="btn btn-success btn-sm" onclick="quickAddServer('${i.instance_id}','${i.display_name}')">+ Add</button>`
                  }
                </div>
              </div>`).join('')}
          </div>
        </div>`;
    }
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    btn.disabled = false; btn.textContent = '🔍 Discover from AWS';
  }
});

window.quickAddServer = async function(instanceId, displayName) {
  try {
    await api.post('/api/admin/servers', {
      instance_id: instanceId, type: 'EC2',
      display_name: displayName, region: 'ap-south-1',
    });
    showToast(`${displayName} added to CSR`, 'success');
    loadServers();
  } catch (err) {
    showToast(err.message, 'error');
  }
};

document.getElementById('openAddServerBtn').addEventListener('click', () => {
  ['newServerName','newInstanceId'].forEach(id => document.getElementById(id).value = '');
  document.getElementById('newServerType').value = 'EC2';
  document.getElementById('newServerRegion').value = 'ap-south-1';
  document.getElementById('addServerError').style.display = 'none';
  document.getElementById('addServerModal').classList.add('active');
});

document.getElementById('confirmAddServerBtn').addEventListener('click', async () => {
  const btn = document.getElementById('confirmAddServerBtn');
  const errEl = document.getElementById('addServerError');
  errEl.style.display = 'none';

  const body = {
    display_name: document.getElementById('newServerName').value.trim(),
    instance_id:  document.getElementById('newInstanceId').value.trim(),
    type:         document.getElementById('newServerType').value,
    region:       document.getElementById('newServerRegion').value.trim() || 'ap-south-1',
  };

  if (!body.display_name || !body.instance_id) {
    errEl.textContent = 'Name and Instance ID are required.'; errEl.style.display = 'block'; return;
  }

  btn.disabled = true; btn.textContent = 'Adding…';
  try {
    await api.post('/api/admin/servers', body);
    document.getElementById('addServerModal').classList.remove('active');
    showToast(`${body.display_name} added`, 'success');
    loadServers();
  } catch (err) {
    errEl.textContent = err.message; errEl.style.display = 'block';
  } finally {
    btn.disabled = false; btn.textContent = 'Add Server';
  }
});

window.removeServer = async function(serverId, name) {
  if (!confirm(`Remove '${name}' from CSR? The instance will not be deleted from AWS.`)) return;
  try {
    await api.delete(`/api/admin/servers/${serverId}`);
    showToast(`${name} removed from CSR`, 'success');
    loadServers();
  } catch (err) {
    showToast(err.message, 'error');
  }
};

// ─── ACTIVITY TAB ──────────────────────────────────────────────

let allActivity = [];

async function loadActivity() {
  const tbody = document.getElementById('activityBodyAdmin');
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-muted);">Loading…</td></tr>';
  try {
    allActivity = await api.get('/api/admin/activity');
    renderActivity(allActivity);
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--danger);">${err.message}</td></tr>`;
  }
}

function renderActivity(rows) {
  const tbody = document.getElementById('activityBodyAdmin');
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:32px;color:var(--text-muted);">No activity recorded yet</td></tr>';
    return;
  }
  const actionColors = {
    LOGIN: 'badge-info', LOGOUT: 'badge-muted',
    EXTEND_INSTANCE: 'badge-success', STOP_INSTANCE: 'badge-danger',
    FAILED_LOGIN: 'badge-danger', ADD_USER: 'badge-purple',
    REMOVE_USER: 'badge-danger', UPDATE_USER: 'badge-warning',
    ADD_SERVER: 'badge-orange', REMOVE_SERVER: 'badge-danger',
  };
  tbody.innerHTML = rows.slice(0, 200).map(a => `
    <tr>
      <td>
        <div style="display:flex;align-items:center;gap:8px;">
          <div class="user-avatar" style="width:24px;height:24px;font-size:0.65rem;">${(a.username||'?').slice(0,2).toUpperCase()}</div>
          <span style="font-size:0.875rem;font-weight:500;">${a.username}</span>
        </div>
      </td>
      <td><span class="badge ${actionColors[a.action] || 'badge-muted'}" style="font-size:0.7rem;">${a.action}</span></td>
      <td class="mono" style="font-size:0.78rem;color:var(--text-muted);">${a.resource_id || '—'}</td>
      <td style="font-size:0.82rem;color:var(--text-secondary);max-width:300px;" title="${a.details||''}">${(a.details||'—').slice(0,80)}${(a.details||'').length > 80 ? '…' : ''}</td>
      <td style="font-size:0.8rem;white-space:nowrap;">${formatDate(a.timestamp)}</td>
      <td class="mono" style="font-size:0.78rem;color:var(--text-muted);">${a.ip_address||'—'}</td>
    </tr>`).join('');
}

document.getElementById('activitySearch').addEventListener('input', e => {
  const q = e.target.value.toLowerCase();
  const filtered = allActivity.filter(a =>
    (a.username||'').toLowerCase().includes(q) ||
    (a.action||'').toLowerCase().includes(q) ||
    (a.resource_id||'').toLowerCase().includes(q) ||
    (a.details||'').toLowerCase().includes(q)
  );
  renderActivity(filtered);
});

// ─── REPORTS TAB ────────────────────────────────────────────────

async function loadReports() {
  const tbody = document.getElementById('reportBody');
  const chart = document.getElementById('chartContainer');
  tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--text-muted);">Loading…</td></tr>';
  try {
    const rows = await api.get('/api/admin/reports/extra-hours');
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:32px;color:var(--text-muted);">No extension data yet</td></tr>';
      chart.innerHTML = '<p style="text-align:center;padding:24px;color:var(--text-muted);">No data yet</p>';
      return;
    }

    // Bar chart
    const maxH = Math.max(...rows.map(r => r.extra_hours), 1);
    chart.innerHTML = rows.slice(0, 10).map(r => `
      <div style="display:flex;align-items:center;gap:12px;">
        <div style="width:180px;font-size:0.82rem;color:var(--text-secondary);
                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
                    text-align:right;">${r.display_name}</div>
        <div style="flex:1;height:20px;background:var(--bg-primary);border-radius:4px;overflow:hidden;">
          <div style="height:100%;width:${Math.max(2, (r.extra_hours/maxH)*100)}%;
                      background:linear-gradient(90deg,var(--orange),var(--purple-light));
                      border-radius:4px;transition:width 0.8s ease;"></div>
        </div>
        <div style="width:60px;font-size:0.82rem;font-weight:600;color:var(--orange);">${r.extra_hours}h</div>
      </div>`).join('');

    // Table
    const statusColors = { active:'badge-success', expired:'badge-muted', manually_stopped:'badge-warning' };
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td>
          <div><strong style="font-size:0.875rem;">${r.display_name}</strong></div>
          <div class="mono" style="font-size:0.75rem;color:var(--text-muted);">${r.instance_id}</div>
        </td>
        <td>${typeBadge(r.instance_type)}</td>
        <td style="font-size:0.875rem;">${r.username}</td>
        <td style="font-size:0.82rem;">${formatDate(r.extended_until)}</td>
        <td><span class="badge ${statusColors[r.status]||'badge-muted'}">${r.status}</span></td>
        <td>
          <strong style="color:${r.extra_hours > 4 ? 'var(--danger)' : r.extra_hours > 2 ? 'var(--warning)' : 'var(--success)'};">
            ${r.extra_hours}h
          </strong>
        </td>
      </tr>`).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:24px;color:var(--danger);">${err.message}</td></tr>`;
  }
}

document.getElementById('refreshReportBtn').addEventListener('click', loadReports);

// ─── LEADERBOARD TAB ────────────────────────────────────────────

async function loadLeaderboard() {
  const tbody    = document.getElementById('leaderboardBody');
  const podium   = document.getElementById('podiumContainer');
  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-muted);">Loading…</td></tr>';
  try {
    const board = await api.get('/api/admin/reports/leaderboard');
    if (!board.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:32px;color:var(--text-muted);">No data yet — leaderboard populates after extensions are made.</td></tr>';
      podium.innerHTML = '';
      return;
    }

    // Podium (top 3)
    const podiumOrder = [board[1], board[0], board[2]].filter(Boolean);
    const podiumRanks  = [2, 1, 3];
    podium.innerHTML = podiumOrder.map((u, i) => {
      const rankNum = podiumRanks[i];
      const medal   = ['🥇','🥈','🥉'][rankNum - 1];
      return `
        <div class="podium-item rank-${rankNum}">
          <div style="font-size:0.8rem;font-weight:600;color:var(--text-secondary);">${u.username}</div>
          <div class="podium-avatar">
            ${u.username.slice(0,2).toUpperCase()}
            <span class="podium-rank-badge">${rankNum}</span>
          </div>
          <div class="podium-stand">${medal} ${u.total_extra_hours}h</div>
        </div>`;
    }).join('');

    // Table
    tbody.innerHTML = board.map(u => `
      <tr>
        <td>
          <strong style="color:${u.rank<=3?'var(--orange)':'var(--text-muted)'};">
            ${u.rank <= 3 ? ['🥇','🥈','🥉'][u.rank-1] : `#${u.rank}`}
          </strong>
        </td>
        <td>
          <div style="display:flex;align-items:center;gap:8px;">
            <div class="user-avatar" style="width:28px;height:28px;font-size:0.7rem;">${u.username.slice(0,2).toUpperCase()}</div>
            <strong style="font-size:0.875rem;">${u.username}</strong>
          </div>
        </td>
        <td style="font-size:0.875rem;">${u.total_extensions}</td>
        <td>${u.active_extensions > 0
          ? `<span class="badge badge-success">${u.active_extensions} active</span>`
          : '<span class="badge badge-muted">None</span>'}</td>
        <td>
          <strong style="color:${u.total_extra_hours > 20 ? 'var(--danger)' : u.total_extra_hours > 8 ? 'var(--warning)' : 'var(--success)'};">
            ${u.total_extra_hours}h
          </strong>
        </td>
      </tr>`).join('');
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--danger);">${err.message}</td></tr>`;
    podium.innerHTML = '';
  }
}

// ─── Logout ────────────────────────────────────────────────────

document.getElementById('logoutBtn').addEventListener('click', () => {
  if (confirm('Sign out of CSR Admin?')) logout();
});

// ─── Init ──────────────────────────────────────────────────────

loadTab('users');
