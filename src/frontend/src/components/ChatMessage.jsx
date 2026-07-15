import { useId, useState } from 'react';
import { formatText } from '../utils/markdown.js';
import { responseBadgeLabel, sourceDisplayLabels } from '../utils/presentationMetadata.js';
import DebugPanel from './DebugPanel.jsx';

export default function ChatMessage({ msg }) {
  const [detailsOpen, setDetailsOpen] = useState(false);
  const detailPanelId = useId();
  const isUser = msg.role === 'user';
  const data = msg.data || null;
  const sourceLabels = sourceDisplayLabels(data);
  const graphFacts = Array.isArray(data?.graph_facts) ? data.graph_facts : [];
  const hasMetadata = Boolean(data?.metadata && Object.keys(data.metadata).length > 0);
  const hasAnswerDetails = Boolean(data && (sourceLabels.length > 0 || hasMetadata || graphFacts.length > 0));

  return (
    <div className={`chat-message ${isUser ? 'chat-message-user' : 'chat-message-assistant'}`}>
      <div className="chat-message-inner">
        {/* Content */}
        <div className="chat-message-content">
          {isUser ? (
            <div className="chat-user-text">{msg.content}</div>
          ) : (
            <div className="chat-assistant-text">
              <div className="chat-formatted-text">{formatText(msg.content)}</div>

              {data && (
                <div className="chat-message-extras">
                  {/* Symptoms rendering removed as requested to hide keywords from UI */}

                  {/* Safety Flags */}
                  {data.safety_flags && data.safety_flags.length > 0 && (
                    <div className="chat-safety-flags">
                      <svg
                        width="20"
                        height="20"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        className="safety-icon"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="2"
                          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                        />
                      </svg>
                      <div>
                        <strong>Lưu ý:</strong> {data.safety_flags.join(' ')}
                      </div>
                    </div>
                  )}

                  {hasAnswerDetails && (
                    <div className="answer-details">
                      <button
                        type="button"
                        className="answer-details-toggle"
                        aria-expanded={detailsOpen}
                        aria-controls={detailPanelId}
                        onClick={() => setDetailsOpen((open) => !open)}
                      >
                        <span>Chi tiết</span>
                        <svg width="14" height="14" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth="2"
                            d={detailsOpen ? 'M5 15l7-7 7 7' : 'M19 9l-7 7-7-7'}
                          />
                        </svg>
                      </button>

                      {detailsOpen && (
                        <div id={detailPanelId} className="answer-details-panel">
                          {sourceLabels.length > 0 && (
                            <div className="chat-meta-sources">
                              <span className="chat-meta-label">Nguồn: </span>
                              {sourceLabels.join(', ')}
                            </div>
                          )}
                          {hasMetadata && (
                            <div className="chat-meta-info">
                              <span title="Mô hình ngôn ngữ">
                                {responseBadgeLabel(data.metadata)}
                              </span>
                              {data.metadata.retrieval && (
                                <span title="Phương pháp truy xuất">🔍 {data.metadata.retrieval}</span>
                              )}
                              {data.metadata.guardrail === 'out_of_domain' && (
                                <span className="guardrail-badge guardrail-out" title="Ngoài phạm vi hỗ trợ">
                                  Ngoài lề
                                </span>
                              )}
                              {data.metadata.guardrail === 'partial_out_of_domain' && (
                                <span
                                  className="guardrail-badge guardrail-partial"
                                  title="Đã lọc một phần ngoài lề"
                                >
                                  Lọc ngoài lề
                                </span>
                              )}
                            </div>
                          )}
                          <DebugPanel graphFacts={graphFacts} />
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
