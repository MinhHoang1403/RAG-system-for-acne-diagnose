import React from 'react';
import { formatText } from '../utils/markdown.jsx';
import DebugPanel from './DebugPanel.jsx';

export default function ChatMessage({ msg }) {
  const isUser = msg.role === 'user';
  const data = msg.data || null;

  return (
    <div className="chat-message">
      <div className="chat-message-inner">
        {/* Avatar */}
        <div className="chat-avatar-wrapper">
          {isUser ? (
            <div className="chat-avatar chat-avatar-user">U</div>
          ) : (
            <div className="chat-avatar chat-avatar-assistant">
              <svg width="20" height="20" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
            </div>
          )}
        </div>

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

                  {/* Graph Facts / Debug */}
                  <DebugPanel graphFacts={data.graph_facts} />

                  {/* Sources & Metadata */}
                  <div className="chat-meta-row">
                    {data.sources && data.sources.length > 0 && (
                      <div className="chat-meta-sources">
                        <span className="chat-meta-label">Nguồn: </span>
                        {data.sources.join(', ')}
                      </div>
                    )}
                    {data.metadata && (
                      <div className="chat-meta-info">
                        <span title="Mô hình ngôn ngữ">
                          {(() => {
                            const meta = data.metadata;
                            if (meta.provider === 'system' || meta.model === 'guardrail-rule') return '🛡️ Guardrail';
                            if (meta.cache && meta.cache.hit) {
                              const origProv = meta.cached_from_provider === 'gemini' ? 'Gemini 2.5 Flash' : 'Ollama';
                              let fbName = meta.cached_from_model || origProv;
                              if (fbName.includes('qwen2')) fbName = 'Qwen2.5 Local';
                              else if (fbName.includes('qwen3')) fbName = 'Qwen3 Local';
                              else if (fbName.includes('gemini')) fbName = 'Gemini 2.5 Flash';
                              return `♻️ Cached · originally answered by ${fbName}`;
                            }
                            if (meta.fallback_used && meta.fallback_provider) {
                              const origName = meta.provider === 'gemini' ? 'Gemini' : 'Ollama';
                              let fbName = meta.fallback_model;
                              if (meta.fallback_provider === 'gemini') fbName = 'Gemini 2.5 Flash';
                              else if (meta.fallback_model && meta.fallback_model.includes('qwen2')) fbName = 'Qwen2.5 Local';
                              else if (meta.fallback_model && meta.fallback_model.includes('qwen3')) fbName = 'Qwen3 Local';
                              else if (meta.fallback_provider === 'rule_based') fbName = 'Rule-based';
                              return `⚠️ Fallback: ${origName} → ${fbName}`;
                            }
                            if (meta.provider === 'gemini') return '⚡ Gemini 2.5 Flash';
                            if (meta.provider === 'ollama') {
                              if (meta.model && meta.model.includes('qwen2')) return '🖥️ Qwen2.5 Local';
                              if (meta.model && meta.model.includes('qwen3')) return '🖥️ Qwen3 Local';
                              return `🖥️ ${meta.model} Local`;
                            }
                            return `⚡ ${meta.model}`;
                          })()}
                        </span>
                        <span title="Phương pháp truy xuất">🔍 {data.metadata.retrieval}</span>
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
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
