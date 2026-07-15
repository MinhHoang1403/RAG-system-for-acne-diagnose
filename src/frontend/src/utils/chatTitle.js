const DEFAULT_TITLE_PATTERN = /^(đoạn chat mới|new chat|untitled|cuộc trò chuyện mới)$/iu;
const MAX_CHAT_TITLE_LENGTH = 46;

function collapseWhitespace(value) {
  return value.replace(/\s+/g, ' ').trim();
}

function removeLeadingPromptNoise(value) {
  let cleaned = value;
  const prefixPatterns = [
    /^\s*(?:[-*•]\s*)+/u,
    /^\s*(?:câu|question)\s*\d+\s*[).:：-]\s*/iu,
    /^\s*\d+\s*[).:：-]\s*/u,
  ];

  let changed = true;
  while (changed) {
    changed = false;
    for (const pattern of prefixPatterns) {
      const next = cleaned.replace(pattern, '');
      if (next !== cleaned) {
        cleaned = next;
        changed = true;
      }
    }
  }

  return cleaned
    .replace(/^(hãy|vui lòng|làm ơn)\s+/iu, '')
    .replace(/^cho tôi\s+/iu, '')
    .trim();
}

function stripTrailingSentencePunctuation(value) {
  return value.replace(/[.!?。！？]+$/u, '').trim();
}

function capitalizeFirstLetter(value) {
  if (!value) return value;
  return value.charAt(0).toLocaleUpperCase('vi-VN') + value.slice(1);
}

function truncateAtWord(value, maxLength = MAX_CHAT_TITLE_LENGTH) {
  if (value.length <= maxLength) return stripTrailingSentencePunctuation(value);

  const roughCut = value.slice(0, maxLength + 1);
  const lastSpace = roughCut.lastIndexOf(' ');
  const cutPoint = lastSpace >= Math.floor(maxLength * 0.55) ? lastSpace : maxLength;
  return `${stripTrailingSentencePunctuation(value.slice(0, cutPoint))}...`;
}

export function deriveChatTitleFromFirstUserMessage(message) {
  const raw = typeof message === 'string' ? message : '';
  const cleaned = capitalizeFirstLetter(
    stripTrailingSentencePunctuation(
      removeLeadingPromptNoise(
        collapseWhitespace(raw)
          .replace(/^["'“”‘’]+|["'“”‘’]+$/gu, '')
      )
    )
  );

  return truncateAtWord(cleaned) || 'Đoạn chat mới';
}

export function deriveChatTitleFromMessages(messages) {
  const firstUserMessage = (Array.isArray(messages) ? messages : []).find(
    (message) => message?.role === 'user' && typeof message.content === 'string' && message.content.trim()
  );

  return deriveChatTitleFromFirstUserMessage(firstUserMessage?.content || '');
}

export function shouldGenerateSessionTitle(currentTitle, messages = []) {
  const hasUserMessage = (Array.isArray(messages) ? messages : []).some((message) => message?.role === 'user');
  const normalizedTitle = collapseWhitespace(String(currentTitle || ''));
  return !hasUserMessage && (!normalizedTitle || DEFAULT_TITLE_PATTERN.test(normalizedTitle));
}
