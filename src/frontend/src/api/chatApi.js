const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';

export async function parseApiError(response, fallbackPrefix = 'Lỗi server') {
  let detail;
  try {
    const data = await response.clone().json();
    detail = data?.detail || data;
  } catch {
    detail = null;
  }

  const message = typeof detail === 'object' && detail?.message
    ? detail.message
    : `${fallbackPrefix}: ${response.status}`;
  const error = new Error(message);
  error.status = response.status;
  if (typeof detail === 'object' && detail) {
    error.code = detail.code;
    error.retryable = detail.retryable;
    error.errorType = detail.error_type;
  }
  return error;
}

function normalizeListResponse(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.value)) return data.value;
  if (data && Array.isArray(data.Value)) return data.Value;
  return [];
}

/**
 * Send a chat message to the backend.
 * @param {Object} params
 * @param {string} params.message - The user's message text.
 * @param {string|null} params.sessionId - Current session ID.
 * @param {Array<{role: string, content: string}>} params.conversationHistory - Recent conversation history (max 6).
 * @returns {Promise<Object>} The API response data (includes session_id).
 */
export async function sendChatMessage({
  message,
  sessionId,
  conversationHistory = [],
  llmProvider,
  llmModel,
  allowModelFallback,
  bypassCache = false,
}) {
  const response = await fetch(`${API_BASE_URL}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      user_id: null,
      session_id: sessionId,
      conversation_history: conversationHistory,
      llm_provider: llmProvider,
      llm_model: llmModel,
      allow_model_fallback: allowModelFallback,
      bypass_cache: bypassCache,
    }),
  });

  if (!response.ok) {
    throw await parseApiError(response);
  }

  return response.json();
}

/**
 * Check if the backend is reachable.
 * @returns {Promise<boolean>}
 */
export async function checkBackendHealth() {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: 'GET',
      signal: AbortSignal.timeout(3000),
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Fetch available models from backend.
 * @returns {Promise<Object>}
 */
export async function fetchModels() {
  const response = await fetch(`${API_BASE_URL}/models`);
  if (!response.ok) throw await parseApiError(response);
  return response.json();
}

/**
 * Fetch chat sessions from the backend.
 * @param {string|null} userId
 * @param {boolean} includeHidden
 * @returns {Promise<Array>}
 */
export async function fetchSessions(userId = null, includeHidden = false) {
  const params = new URLSearchParams();
  if (userId) params.set('user_id', userId);
  if (includeHidden) params.set('include_hidden', 'true');

  const response = await fetch(`${API_BASE_URL}/chat/sessions?${params.toString()}`);
  if (!response.ok) throw await parseApiError(response);
  const data = await response.json();
  return normalizeListResponse(data);
}

/**
 * Fetch messages for a specific session.
 * @param {string} sessionId
 * @returns {Promise<Array>}
 */
export async function fetchMessages(sessionId) {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/messages`);
  if (!response.ok) throw await parseApiError(response);
  const data = await response.json();
  return normalizeListResponse(data);
}

/**
 * Rename a chat session on the backend.
 * @param {string} sessionId
 * @param {string} title
 * @returns {Promise<Object>}
 */
export async function renameSession(sessionId, title) {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/rename`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) throw await parseApiError(response);
  return response.json();
}

/**
 * Hide a chat session on the backend (sets hidden=true, does NOT delete).
 * @param {string} sessionId
 * @returns {Promise<Object>}
 */
export async function hideSession(sessionId) {
  const response = await fetch(`${API_BASE_URL}/chat/sessions/${sessionId}/hide`, {
    method: 'PATCH',
  });
  if (!response.ok) throw await parseApiError(response);
  return response.json();
}

/**
 * Delete all persisted chat history and app-owned answer cache.
 * @returns {Promise<Object>} deletion counts
 */
export async function deleteAllChatSessions() {
  const response = await fetch(`${API_BASE_URL}/chat/sessions`, {
    method: 'DELETE',
  });
  if (!response.ok) throw await parseApiError(response);
  return response.json();
}

/**
 * Sync localStorage sessions to the backend.
 * @param {Array} sessions - Array of session objects with messages.
 * @returns {Promise<Object>} { synced, skipped, errors }
 */
export async function syncSessionsToBackend(sessions) {
  // Transform sessions to match backend SyncRequest format
  const payload = sessions.map((s) => ({
    id: s.id,
    title: s.title || 'Đoạn chat mới',
    created_at: s.createdAt || null,
    updated_at: s.updatedAt || null,
    hidden: s.hidden || false,
    messages: (s.messages || []).map((m, idx) => ({
      id: m.id || `${s.id}_msg_${idx}`,
      role: m.role,
      content: m.content,
      sources: m.data?.sources || null,
      symptoms: m.data?.symptoms || null,
      safety_flags: m.data?.safety_flags || null,
      graph_facts: m.data?.graph_facts || null,
      metadata: m.data?.metadata ? {
        model: m.data.metadata.model,
        retrieval: m.data.metadata.retrieval,
        guardrail: m.data.metadata.guardrail,
      } : null,
      created_at: m.createdAt || null,
    })),
  }));

  const response = await fetch(`${API_BASE_URL}/chat/sessions/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sessions: payload }),
  });

  if (!response.ok) throw await parseApiError(response, 'Sync failed');
  return response.json();
}
