/**
 * API client for the LLM Council backend.
 *
 * Uses relative URLs: in production the backend serves the built frontend
 * same-origin; in development Vite proxies /api to localhost:8001.
 */

const TOKEN_KEY = 'llm_council_token';

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

function authHeaders() {
  const token = getAuthToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    throw new ApiError(`Request failed: ${path} (${response.status})`, response.status);
  }
  return response;
}

export const api = {
  /**
   * Verify the stored access token (or that auth is disabled).
   */
  async checkAuth() {
    const response = await request('/api/auth/check');
    return response.json();
  },

  /**
   * List all conversations.
   */
  async listConversations() {
    const response = await request('/api/conversations');
    return response.json();
  },

  /**
   * Create a new conversation.
   */
  async createConversation() {
    const response = await request('/api/conversations', {
      method: 'POST',
      body: JSON.stringify({}),
    });
    return response.json();
  },

  /**
   * Get a specific conversation.
   */
  async getConversation(conversationId) {
    const response = await request(`/api/conversations/${conversationId}`);
    return response.json();
  },

  /**
   * Delete a conversation.
   */
  async deleteConversation(conversationId) {
    const response = await request(`/api/conversations/${conversationId}`, {
      method: 'DELETE',
    });
    return response.json();
  },

  /**
   * Send a message and receive streaming updates.
   * @param {string} conversationId - The conversation ID
   * @param {string} content - The message content
   * @param {object} options - { mode: 'full'|'quick', webSearch: boolean }
   * @param {function} onEvent - Callback for each event: (eventType, event) => void
   */
  async sendMessageStream(conversationId, content, options, onEvent) {
    const response = await fetch(
      `/api/conversations/${conversationId}/message/stream`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...authHeaders(),
        },
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

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    // Buffer across chunks: a single SSE event can span multiple reads
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        for (const line of rawEvent.split('\n')) {
          if (line.startsWith('data: ')) {
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
  },
};
