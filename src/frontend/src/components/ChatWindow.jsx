import React, { useRef, useEffect } from 'react';
import ChatMessage from './ChatMessage.jsx';
import EmptyState from './EmptyState.jsx';
import ChatInput from './ChatInput.jsx';

export default function ChatWindow({
  activeSession,
  chatHistory,
  isLoading,
  error,
  message,
  setMessage,
  onSubmit,
  onSendQuestion,
  sidebarOpen,
  onToggleSidebar,
}) {
  const messagesEndRef = useRef(null);

  // Scroll to bottom on new messages or loading state change
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [chatHistory, isLoading]);

  return (
    <div className="chat-window">
      {/* Header */}
      <header className="chat-header">
        <button
          className="sidebar-toggle-btn"
          onClick={onToggleSidebar}
          title="Ẩn/Hiện lịch sử"
        >
          <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M4 6h16M4 12h16M4 18h16"
            />
          </svg>
        </button>
        <div className="chat-header-title">
          <h1>{activeSession ? activeSession.title : 'Đoạn chat mới'}</h1>
        </div>
      </header>

      {/* Chat Scrollable Area */}
      <div className="chat-scroll-area">
        {chatHistory.length === 0 ? (
          <EmptyState onSendQuestion={onSendQuestion} />
        ) : (
          <div className="chat-messages-list">
            {chatHistory.map((msg, index) => (
              <ChatMessage key={index} msg={msg} />
            ))}

            {/* Loading indicator */}
            {isLoading && (
              <div className="chat-message">
                <div className="chat-message-inner">
                  <div className="chat-avatar-wrapper">
                    <div className="chat-avatar chat-avatar-assistant">
                      <svg
                        width="20"
                        height="20"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        className="loading-pulse"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="2"
                          d="M13 10V3L4 14h7v7l9-11h-7z"
                        />
                      </svg>
                    </div>
                  </div>
                  <div className="chat-message-content loading-dots-wrapper">
                    <div className="loading-dots">
                      <div className="loading-dot" />
                      <div className="loading-dot" style={{ animationDelay: '0.15s' }} />
                      <div className="loading-dot" style={{ animationDelay: '0.3s' }} />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Error message */}
            {error && (
              <div className="chat-message">
                <div className="chat-message-inner">
                  <div style={{ width: '32px', flexShrink: 0 }} />
                  <div className="chat-error">
                    <svg
                      width="20"
                      height="20"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      className="error-icon"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                      />
                    </svg>
                    {error}
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} style={{ height: '16px' }} />
          </div>
        )}
      </div>

      {/* Input Area */}
      <ChatInput message={message} setMessage={setMessage} isLoading={isLoading} onSubmit={onSubmit} />
    </div>
  );
}
