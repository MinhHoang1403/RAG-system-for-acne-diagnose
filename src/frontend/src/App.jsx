import React, { useState, useEffect, useCallback, useRef } from 'react';
import Sidebar from './components/Sidebar.jsx';
import ChatWindow from './components/ChatWindow.jsx';
import {
  sendChatMessage,
  checkBackendHealth,
  fetchSessions,
  fetchMessages,
  renameSession as apiRenameSession,
  hideSession as apiHideSession,
  syncSessionsToBackend,
  deleteAllChatSessions,
} from './api/chatApi.js';
import {
  loadSessions,
  saveSessions,
  loadActiveSessionId,
  saveActiveSessionId,
  loadHistoryHiddenAt,
  saveHistoryHiddenAt,
  generateId,
  clearLocalChatCache,
} from './utils/storage.js';

export default function App() {
  // ── State ──────────────────────────────────────────────
  const [sessions, setSessions] = useState(() => loadSessions());
  const [activeSessionId, setActiveSessionId] = useState(() => loadActiveSessionId());
  const [message, setMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [backendOnline, setBackendOnline] = useState(true); // assume online initially
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [historyHiddenAt, setHistoryHiddenAt] = useState(() => loadHistoryHiddenAt());

  // Track whether initial load from backend has been done
  const initialLoadDone = useRef(false);
  const syncDone = useRef(false);

  // ── Derived ────────────────────────────────────────────
  const activeSession = sessions.find((s) => s.id === activeSessionId) || null;
  const chatHistory = activeSession ? activeSession.messages : [];

  // ── Persistence to localStorage ────────────────────────
  useEffect(() => {
    saveSessions(sessions);
  }, [sessions]);

  useEffect(() => {
    saveActiveSessionId(activeSessionId);
  }, [activeSessionId]);

  useEffect(() => {
    saveHistoryHiddenAt(historyHiddenAt);
  }, [historyHiddenAt]);

  // ── Initial Load: check backend & load sessions ────────
  useEffect(() => {
    if (initialLoadDone.current) return;
    initialLoadDone.current = true;

    (async () => {
      const online = await checkBackendHealth();
      setBackendOnline(online);

      if (online) {
        try {
          const backendSessions = await fetchSessions();
          const normalizedBackendSessions = backendSessions.map((s) => ({
            id: s.id,
            title: s.title,
            createdAt: new Date(s.created_at).getTime(),
            updatedAt: new Date(s.updated_at).getTime(),
            hidden: s.hidden,
            messages: [], // Will be loaded on-demand when selected
            _fromBackend: true,
          }));

          setBackendOnline(true);
          setSessions(normalizedBackendSessions);

          const backendIds = new Set(normalizedBackendSessions.map((s) => s.id));
          if (!activeSessionId || !backendIds.has(activeSessionId)) {
            setActiveSessionId(normalizedBackendSessions[0]?.id || null);
          }
        } catch (err) {
          console.warn('Failed to load sessions from backend:', err);
          setBackendOnline(false);
        }
      }
    })();
  }, []);

  // ── Sync localStorage sessions to backend ──────────────
  async function _syncLocalStorageToBackend(lsSessions) {
    // Only sync sessions that have messages
    const toSync = lsSessions.filter((s) => s.messages && s.messages.length > 0);
    if (toSync.length === 0) return;

    try {
      const result = await syncSessionsToBackend(toSync);
      console.info(`Sync complete: ${result.synced} synced, ${result.skipped} skipped, ${result.errors} errors`);
    } catch (err) {
      console.warn('Sync failed (non-critical):', err);
    }
  }

  // ── Load messages from backend when selecting a session ─
  const _loadMessagesFromBackend = useCallback(async (sessionId) => {
    if (!backendOnline) return;

    setLoadingMessages(true);
    try {
      const msgs = await fetchMessages(sessionId);
      if (msgs && msgs.length > 0) {
        const formattedMsgs = msgs.map((m) => ({
          role: m.role,
          content: m.content,
          id: m.id,
          data: m.role === 'assistant' ? {
            answer: m.content,
            sources: m.sources || [],
            symptoms: m.symptoms || [],
            safety_flags: m.safety_flags || [],
            graph_facts: m.graph_facts || [],
            metadata: m.metadata || {},
          } : undefined,
        }));

        setSessions((prev) =>
          prev.map((s) => {
            if (s.id === sessionId) {
              return { ...s, messages: formattedMsgs, _fromBackend: true };
            }
            return s;
          })
        );
      }
    } catch (err) {
      console.warn('Failed to load messages from backend:', err);
    } finally {
      setLoadingMessages(false);
    }
  }, [backendOnline]);

  // ── Handlers ───────────────────────────────────────────
  const handleNewChat = useCallback(() => {
    setActiveSessionId(null);
    setError(null);
    setMessage('');
  }, []);

  const handleSelectSession = useCallback(
    (id) => {
      setActiveSessionId(id);
      setError(null);
      if (window.innerWidth < 768) {
        setSidebarOpen(false);
      }

      // Load messages from backend if this session came from backend
      // and doesn't have messages loaded yet
      const session = sessions.find((s) => s.id === id);
      if (session && session._fromBackend && (!session.messages || session.messages.length === 0)) {
        _loadMessagesFromBackend(id);
      } else if (backendOnline && session) {
        // Even if we have local messages, refresh from backend to get latest
        _loadMessagesFromBackend(id);
      }
    },
    [sessions, backendOnline, _loadMessagesFromBackend]
  );

  const handleRenameSession = useCallback(async (id, newTitle) => {
    // Always update local state first
    setSessions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, title: newTitle, updatedAt: Date.now() } : s))
    );

    // Then sync to backend if online
    if (backendOnline) {
      try {
        await apiRenameSession(id, newTitle);
      } catch (err) {
        console.warn('Failed to rename session on backend:', err);
      }
    }
  }, [backendOnline]);

  const handleHideSession = useCallback(
    async (id) => {
      // Update local state — only set hidden, never delete
      setSessions((prev) =>
        prev.map((s) => (s.id === id ? { ...s, hidden: true, updatedAt: Date.now() } : s))
      );

      // If the hidden session was the active one, switch to the most recent visible session
      if (activeSessionId === id) {
        const remaining = sessions
          .filter((s) => s.id !== id && !s.hidden)
          .sort((a, b) => b.updatedAt - a.updatedAt);
        setActiveSessionId(remaining.length > 0 ? remaining[0].id : null);
      }

      // Sync to backend if online
      if (backendOnline) {
        try {
          await apiHideSession(id);
        } catch (err) {
          console.warn('Failed to hide session on backend:', err);
        }
      }
    },
    [activeSessionId, sessions, backendOnline]
  );

  const handleClearLocalHistory = useCallback(() => {
    clearLocalChatCache();
    setSessions([]);
    setActiveSessionId(null);
    setHistoryHiddenAt(null);
  }, []);

  const handleHideAllSessions = useCallback(() => {
    setHistoryHiddenAt(Date.now());
    setActiveSessionId(null);
    setError(null);
  }, []);

  const handleShowHistory = useCallback(() => {
    setHistoryHiddenAt(null);
  }, []);

  const handleDeleteAllSessions = useCallback(async () => {
    const confirmed = window.confirm(
      'Bạn có chắc muốn xoá toàn bộ lịch sử chat? Hành động này sẽ xoá dữ liệu trong PostgreSQL và cache Redis liên quan, không thể hoàn tác.'
    );
    if (!confirmed) return;

    try {
      const result = await deleteAllChatSessions();
      console.info('Deleted chat history:', result);
      clearLocalChatCache();
      setSessions([]);
      setActiveSessionId(null);
      setHistoryHiddenAt(null);
      setError(null);

      if (backendOnline) {
        const backendSessions = await fetchSessions();
        const normalizedBackendSessions = backendSessions.map((s) => ({
          id: s.id,
          title: s.title,
          createdAt: new Date(s.created_at).getTime(),
          updatedAt: new Date(s.updated_at).getTime(),
          hidden: s.hidden,
          messages: [],
          _fromBackend: true,
        }));
        setSessions(normalizedBackendSessions);
      }
    } catch (err) {
      console.error('Failed to delete all chat history:', err);
      setError('Không xoá được lịch sử chat. Hãy kiểm tra backend rồi thử lại.');
    }
  }, [backendOnline]);

  const sendQuestion = useCallback(
    async (userMessageText, modelConfig = null) => {
      if (!userMessageText.trim() || isLoading) return;

      setError(null);
      setIsLoading(true);

      let currentSessionId = activeSessionId;

      // Create a new session if none is active
      if (!currentSessionId) {
        currentSessionId = generateId();
        const title =
          userMessageText.length > 40
            ? userMessageText.substring(0, 40) + '...'
            : userMessageText;
        const newSession = {
          id: currentSessionId,
          title,
          createdAt: Date.now(),
          updatedAt: Date.now(),
          hidden: false,
          messages: [],
        };
        setSessions((prev) => [newSession, ...prev]);
        setActiveSessionId(currentSessionId);
      }

      // Add user message to session
      const userMsgObj = { role: 'user', content: userMessageText };
      setSessions((prev) =>
        prev.map((s) => {
          if (s.id === currentSessionId) {
            return { ...s, messages: [...s.messages, userMsgObj], updatedAt: Date.now() };
          }
          return s;
        })
      );

      // Compile conversation history (max 6 recent messages, role+content only)
      const currentSessionObj = sessions.find((s) => s.id === currentSessionId) || {
        messages: [],
      };
      const history = currentSessionObj.messages
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content }));

      try {
        const data = await sendChatMessage({
          message: userMessageText,
          sessionId: currentSessionId,
          conversationHistory: history,
          llmProvider: modelConfig?.llmProvider,
          llmModel: modelConfig?.llmModel,
          allowModelFallback: modelConfig?.allowModelFallback,
        });

        // Update session_id from backend response if different
        const responseSessionId = data.session_id || currentSessionId;
        if (responseSessionId !== currentSessionId) {
          // Backend assigned a different session ID — update
          setSessions((prev) =>
            prev.map((s) => {
              if (s.id === currentSessionId) {
                return { ...s, id: responseSessionId };
              }
              return s;
            })
          );
          setActiveSessionId(responseSessionId);
        }

        // Add assistant message
        const assistantMsgObj = { role: 'assistant', content: data.answer, data };
        setSessions((prev) =>
          prev.map((s) => {
            if (s.id === currentSessionId || s.id === responseSessionId) {
              return { ...s, messages: [...s.messages, assistantMsgObj] };
            }
            return s;
          })
        );
      } catch (err) {
        setError('Không kết nối được backend. Hãy kiểm tra FastAPI tại http://127.0.0.1:8000');
        console.error(err);

        // Check if backend went offline
        const stillOnline = await checkBackendHealth();
        setBackendOnline(stillOnline);
      } finally {
        setIsLoading(false);
      }
    },
    [activeSessionId, sessions, isLoading]
  );

  const handleSubmit = useCallback((text, modelConfig) => {
    setMessage('');
    sendQuestion(text, modelConfig);
  }, [sendQuestion]);

  // ── Render ─────────────────────────────────────────────
  return (
    <div className="app-layout">
      <Sidebar
        sessions={sessions}
        activeSessionId={activeSessionId}
        sidebarOpen={sidebarOpen}
        backendOnline={backendOnline}
        onNewChat={handleNewChat}
        onSelectSession={handleSelectSession}
        onRenameSession={handleRenameSession}
        onHideSession={handleHideSession}
        onClearLocalHistory={handleClearLocalHistory}
        historyHidden={historyHiddenAt !== null}
        historyHiddenAt={historyHiddenAt}
        onHideAllSessions={handleHideAllSessions}
        onShowHistory={handleShowHistory}
        onDeleteAllSessions={handleDeleteAllSessions}
      />
      <ChatWindow
        activeSession={activeSession}
        chatHistory={chatHistory}
        isLoading={isLoading || loadingMessages}
        error={error}
        message={message}
        setMessage={setMessage}
        onSubmit={handleSubmit}
        onSendQuestion={sendQuestion}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
      />
    </div>
  );
}
