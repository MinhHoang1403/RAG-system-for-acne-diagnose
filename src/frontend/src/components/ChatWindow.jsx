import { useRef, useEffect } from 'react';
import ChatMessage from './ChatMessage.jsx';
import EmptyState from './EmptyState.jsx';
import ChatInput from './ChatInput.jsx';

export default function ChatWindow({
  chatHistory,
  sidebarOpen = true,
  isLoading,
  error,
  message,
  setMessage,
  onSubmit,
  onSendQuestion,
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
      {!sidebarOpen && (
        <button
          className="sidebar-reopen-btn"
          onClick={onToggleSidebar}
          title="Mở lịch sử chat"
          aria-label="Mở thanh lịch sử chat"
          type="button"
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
      )}

      {/* Chat Scrollable Area */}
      <div className={`chat-scroll-area ${chatHistory.length === 0 ? 'chat-scroll-area-empty' : ''}`}>
        {chatHistory.length === 0 ? (
          <EmptyState onSendQuestion={onSendQuestion} />
        ) : (
          <div className="chat-messages-list">
            {chatHistory.map((msg, index) => (
              <ChatMessage key={index} msg={msg} />
            ))}

            {/* Loading indicator */}
            {isLoading && (
              <div className="chat-message chat-message-assistant">
                <div className="chat-message-inner">
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
              <div className="chat-message chat-message-assistant">
                <div className="chat-message-inner">
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
