/**
 * CSR API Client
 * Wraps fetch() with JWT auth, error handling, and toast notifications.
 */

const API_BASE = (window.CSR_CONFIG?.API_BASE_URL || "").replace(/\/$/, "");
const TOKEN_KEY = "csr_token";
const USER_KEY  = "csr_user";

// ─── Token / User helpers ──────────────────────────────────────

export function getToken()        { return localStorage.getItem(TOKEN_KEY); }
export function setToken(t)       { localStorage.setItem(TOKEN_KEY, t); }
export function removeToken()     { localStorage.removeItem(TOKEN_KEY); }

export function getUser()         { try { return JSON.parse(localStorage.getItem(USER_KEY)); } catch { return null; } }
export function setUser(u)        { localStorage.setItem(USER_KEY, JSON.stringify(u)); }
export function removeUser()      { localStorage.removeItem(USER_KEY); }

export function isLoggedIn()      { return !!getToken(); }
export function isAdmin()         { return getUser()?.role === "admin"; }

export function requireAuth() {
  if (!isLoggedIn()) { window.location.href = "/login.html"; return false; }
  return true;
}

export function requireAdmin() {
  if (!isLoggedIn()) { window.location.href = "/login.html"; return false; }
  if (!isAdmin())    { window.location.href = "/dashboard.html"; return false; }
  return true;
}

// ─── Core fetch wrapper ────────────────────────────────────────

async function request(method, path, body) {
  const headers = { "Content-Type": "application/json" };
  const token = getToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const opts = { method, headers };
  if (body !== undefined) opts.body = JSON.stringify(body);

  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, opts);
  } catch (err) {
    throw new Error("Network error — cannot reach the CSR API");
  }

  if (res.status === 401) {
    removeToken();
    removeUser();
    const isLoginEndpoint = path === "/api/auth/login";
    const isLoginPage = typeof window !== "undefined" && (window.location.pathname.endsWith("/login.html") || window.location.pathname === "/");
    if (!isLoginEndpoint && !isLoginPage) {
      window.location.href = "/login.html";
      return;
    }
  }

  const data = await res.json().catch(() => ({}));

  if (!res.ok) {
    const msg = data.detail || data.message || `HTTP ${res.status}`;
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }

  return data;
}

export const api = {
  get:    (path)         => request("GET",    path),
  post:   (path, body)   => request("POST",   path, body),
  put:    (path, body)   => request("PUT",    path, body),
  delete: (path)         => request("DELETE", path),
  patch:  (path, body)   => request("PATCH",  path, body),
};

// ─── Auth helpers ──────────────────────────────────────────────

export async function login(username, password) {
  const data = await api.post("/api/auth/login", { username, password });
  setToken(data.access_token);
  setUser(data.user);
  return data.user;
}

export async function logout() {
  try { await api.post("/api/auth/logout"); } catch { /* ignore */ }
  removeToken();
  removeUser();
  window.location.href = "/login.html";
}

// ─── Toast system ──────────────────────────────────────────────

let toastContainer = null;

function ensureToastContainer() {
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.className = "toast-container";
    document.body.appendChild(toastContainer);
  }
  return toastContainer;
}

export function showToast(message, type = "info", duration = 4000) {
  const icons = { success: "✅", error: "❌", warning: "⚠️", info: "ℹ️" };
  const container = ensureToastContainer();

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${icons[type] || "ℹ️"}</span><span>${message}</span>`;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = "toast-out 0.3s ease forwards";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ─── Utility helpers ───────────────────────────────────────────

export function formatDate(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date(iso));
}

export function timeUntil(iso) {
  if (!iso) return "";
  const diff = new Date(iso) - Date.now();
  if (diff <= 0) return "Expired";
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  if (h > 0) return `${h}h ${m}m remaining`;
  return `${m}m remaining`;
}

export function statusBadge(state) {
  const map = {
    running:  { label: "Running",  cls: "badge-success" },
    stopped:  { label: "Stopped",  cls: "badge-danger"  },
    stopping: { label: "Stopping", cls: "badge-warning"  },
    pending:  { label: "Starting", cls: "badge-warning"  },
    available:{ label: "Running",  cls: "badge-success"  },
    unknown:  { label: "Unknown",  cls: "badge-muted"   },
  };
  const { label, cls } = map[state] || map.unknown;
  const dotCls = state === "running" || state === "available" ? "running"
               : state === "stopped" ? "stopped"
               : state === "unknown" ? "unknown" : "pending";
  return `<span class="badge ${cls}"><span class="status-dot ${dotCls}"></span>${label}</span>`;
}

export function typeBadge(type) {
  return type === "EC2"
    ? `<span class="badge badge-orange">🖥 EC2</span>`
    : `<span class="badge badge-info">🗄 RDS</span>`;
}

export function initUserDisplay() {
  const user = getUser();
  if (!user) return;
  document.querySelectorAll("[data-user-name]").forEach(el => el.textContent = user.username);
  document.querySelectorAll("[data-user-role]").forEach(el => el.textContent = user.role);
  document.querySelectorAll("[data-user-avatar]").forEach(el => {
    el.textContent = user.username.slice(0, 2).toUpperCase();
  });
}

// ─── In-App Modal Dialog (replaces browser confirm/alert) ───────

export function showConfirm({
  title = "Confirm Action",
  message = "Are you sure you want to proceed?",
  confirmText = "Confirm",
  cancelText = "Cancel",
  type = "danger",
  icon = "⚠️"
} = {}) {
  return new Promise((resolve) => {
    const existing = document.getElementById("csrConfirmOverlay");
    if (existing) existing.remove();

    const overlay = document.createElement("div");
    overlay.id = "csrConfirmOverlay";
    overlay.className = "modal-overlay active";
    overlay.style.zIndex = "2500";

    const btnClass = type === "danger" ? "btn-danger" : type === "warning" ? "btn-warning" : "btn-primary";

    overlay.innerHTML = `
      <div class="modal confirm-modal" style="max-width: 440px; text-align: center;">
        <div style="font-size: 2.6rem; margin-bottom: 12px; line-height: 1;">${icon}</div>
        <h3 style="font-size: 1.25rem; font-weight: 700; color: var(--text-primary); margin-bottom: 8px;">${title}</h3>
        <p style="font-size: 0.92rem; color: var(--text-secondary); line-height: 1.5; margin-bottom: 24px;">${message}</p>
        <div style="display: flex; gap: 12px; justify-content: center;">
          <button id="csrConfirmCancelBtn" class="btn btn-ghost" style="flex: 1; justify-content: center; padding: 11px 18px;">${cancelText}</button>
          <button id="csrConfirmOkBtn" class="btn ${btnClass}" style="flex: 1; justify-content: center; padding: 11px 18px;">${confirmText}</button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    const cleanup = (result) => {
      overlay.classList.remove("active");
      setTimeout(() => overlay.remove(), 220);
      resolve(result);
    };

    overlay.querySelector("#csrConfirmOkBtn").addEventListener("click", () => cleanup(true));
    overlay.querySelector("#csrConfirmCancelBtn").addEventListener("click", () => cleanup(false));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) cleanup(false);
    });
  });
}

