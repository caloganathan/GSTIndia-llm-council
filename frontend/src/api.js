/**
 * API client.
 *
 * By default the API is same-origin: Vite proxies /api to :8001 in
 * development, and in a single-service deployment the backend serves this
 * bundle itself.
 *
 * Set VITE_API_BASE_URL at build time to point the frontend at a backend on a
 * different host — the split deployment where the UI is served from a static
 * host and the API runs elsewhere. Include the scheme and no trailing slash,
 * e.g. https://llm-council.onrender.com
 */

const API_BASE = (import.meta.env?.VITE_API_BASE_URL || '').replace(/\/+$/, '');

/** Resolve an API path against the configured base. */
export function apiUrl(path) {
  return API_BASE ? `${API_BASE}${path}` : path;
}

const TOKEN_KEY = 'llm_council_token';

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function setAuthToken(token) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

function authHeaders() {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  const response = await fetch(apiUrl(path), {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (body.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, response.status);
  }
  return response;
}

async function json(path, options) {
  return (await request(path, options)).json();
}

export const api = {
  // ---- auth ----
  checkAuth: () => json('/api/auth/check'),

  async login(email, password) {
    const response = await fetch(apiUrl('/api/auth/login'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      let detail = 'Invalid email or password';
      try {
        const body = await response.json();
        if (body.detail) detail = body.detail;
      } catch { /* ignore */ }
      throw new ApiError(detail, response.status);
    }
    return response.json();
  },

  logout: () => json('/api/auth/logout', { method: 'POST' }),

  changePassword: (current_password, new_password) =>
    json('/api/auth/password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),

  // ---- panel ----
  panelConfig: () => json('/api/panel/config'),

  /** Upload a notice and get proposed intake fields back. */
  async extractNotice(file, { domain = 'gst', tier } = {}) {
    const body = new FormData();
    body.append('file', file);
    const params = new URLSearchParams({ domain, ...(tier ? { tier } : {}) });
    const response = await fetch(apiUrl(`/api/panel/extract?${params}`), {
      method: 'POST',
      headers: authHeaders(),   // no Content-Type: the browser sets the boundary
      body,
    });
    if (!response.ok) {
      let detail = `Could not read the notice (${response.status})`;
      try {
        const payload = await response.json();
        if (payload.detail) detail = payload.detail;
      } catch { /* non-JSON error body */ }
      throw new ApiError(detail, response.status);
    }
    return response.json();
  },
  dashboard: () => json('/api/dashboard'),
  listMatters: () => json('/api/matters'),
  getMatter: (id) => json(`/api/matters/${id}`),
  deleteMatter: (id) => json(`/api/matters/${id}`, { method: 'DELETE' }),

  exportUrl: (id) => apiUrl(`/api/matters/${id}/export`),

  async downloadMatter(id, filename) {
    const response = await request(`/api/matters/${id}/export`);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename || 'Reply_Pack.docx';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  },

  /** Run the panel, streaming stage events. */
  async runPanel(payload, onEvent) {
    const response = await fetch(apiUrl('/api/panel/run'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new ApiError(`Panel run failed (${response.status})`, response.status);
    }
    await consumeSSE(response, onEvent);
  },

  // ---- admin ----
  adminUsers: () => json('/api/admin/users'),
  createUser: (payload) =>
    json('/api/admin/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (id, payload) =>
    json(`/api/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteUser: (id) => json(`/api/admin/users/${id}`, { method: 'DELETE' }),
  adminSettings: () => json('/api/admin/settings'),
  health: () => json('/api/health'),

  // ---- generic council (retained) ----
  listConversations: () => json('/api/conversations'),
  createConversation: () =>
    json('/api/conversations', { method: 'POST', body: JSON.stringify({}) }),
  getConversation: (id) => json(`/api/conversations/${id}`),
  deleteConversation: (id) => json(`/api/conversations/${id}`, { method: 'DELETE' }),

  async sendMessageStream(conversationId, content, options, onEvent) {
    const response = await fetch(
      apiUrl(`/api/conversations/${conversationId}/message/stream`),
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeaders() },
        body: JSON.stringify({
          content,
          mode: options?.mode || 'full',
          web_search: Boolean(options?.webSearch),
        }),
      }
    );
    if (!response.ok) {
      throw new ApiError(`Failed to send message (${response.status})`, response.status);
    }
    await consumeSSE(response, onEvent);
  },
};

/** Read an SSE stream, buffering across chunk boundaries. */
async function consumeSSE(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const raw = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      for (const line of raw.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        try {
          const event = JSON.parse(line.slice(6));
          onEvent(event.type, event);
        } catch (e) {
          console.error('Failed to parse SSE event:', e);
        }
      }
    }
  }
}
