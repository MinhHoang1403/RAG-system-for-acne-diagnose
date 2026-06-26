/**
 * LocalStorage utilities for chat sessions.
 * Uses the same keys as the legacy frontend to preserve existing chat history.
 *
 * Key: 'acneAdvisorSessions' — JSON array of session objects.
 * Key: 'acneAdvisorActiveSession' — string ID of the active session.
 */

const SESSIONS_KEY = 'acneAdvisorSessions';
const ACTIVE_SESSION_KEY = 'acneAdvisorActiveSession';
const HISTORY_HIDDEN_KEY = 'acneAdvisorHistoryHidden';

/**
 * Load all sessions from localStorage, applying migration for older schemas.
 * @returns {Array} Array of session objects.
 */
export function loadSessions() {
  try {
    const saved = localStorage.getItem(SESSIONS_KEY);
    if (!saved) return [];
    const parsed = JSON.parse(saved);
    // Migrate old sessions: ensure hidden and updatedAt fields exist
    return parsed.map((s) => ({
      ...s,
      hidden: s.hidden || false,
      updatedAt: s.updatedAt || s.createdAt || Date.now(),
    }));
  } catch {
    return [];
  }
}

/**
 * Save sessions array to localStorage.
 * @param {Array} sessions
 */
export function saveSessions(sessions) {
  localStorage.setItem(SESSIONS_KEY, JSON.stringify(sessions));
}

/**
 * Load the active session ID from localStorage.
 * @returns {string|null}
 */
export function loadActiveSessionId() {
  return localStorage.getItem(ACTIVE_SESSION_KEY) || null;
}

/**
 * Save the active session ID to localStorage.
 * @param {string|null} id
 */
export function saveActiveSessionId(id) {
  if (id) {
    localStorage.setItem(ACTIVE_SESSION_KEY, id);
  } else {
    localStorage.removeItem(ACTIVE_SESSION_KEY);
  }
}

export function loadHistoryHiddenAt() {
  const rawValue = localStorage.getItem(HISTORY_HIDDEN_KEY);
  if (!rawValue) return null;

  // Backward compatibility for the previous boolean flag.
  if (rawValue === 'true') return Date.now();

  const parsed = Number(rawValue);
  return Number.isFinite(parsed) ? parsed : null;
}

export function saveHistoryHiddenAt(hiddenAt) {
  if (hiddenAt) {
    localStorage.setItem(HISTORY_HIDDEN_KEY, String(hiddenAt));
  } else {
    localStorage.removeItem(HISTORY_HIDDEN_KEY);
  }
}

/**
 * Clear local chat sessions and active session selection.
 */
export function clearLocalChatCache() {
  localStorage.removeItem(SESSIONS_KEY);
  localStorage.removeItem(ACTIVE_SESSION_KEY);
  localStorage.removeItem(HISTORY_HIDDEN_KEY);
  sessionStorage.removeItem(SESSIONS_KEY);
  sessionStorage.removeItem(ACTIVE_SESSION_KEY);
  sessionStorage.removeItem(HISTORY_HIDDEN_KEY);
}

/**
 * Generate a random session ID.
 * @returns {string}
 */
export function generateId() {
  return Math.random().toString(36).substring(2, 11);
}
