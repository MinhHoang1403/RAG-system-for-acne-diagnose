/**
 * Simple markdown-like text formatter.
 * Converts basic markdown patterns to React elements.
 * Matches the legacy frontend's formatText function.
 *
 * @param {string} text - Raw text to format.
 * @returns {Array<React.ReactElement>} Array of React elements.
 */
export function formatText(text) {
  if (!text) return '';

  return text.split('\n').map((line, i) => {
    // Bold list items: *   **bold** rest  or  -   **bold** rest
    if (line.startsWith('*   **') || line.startsWith('-   **')) {
      const parts = line.split('**');
      return (
        <li key={i} className="chat-list-item">
          <strong>{parts[1]}</strong>
          {parts.slice(2).join('**')}
        </li>
      );
    }

    // Plain list items: *   text  or  -   text
    if (line.startsWith('*   ') || line.startsWith('-   ')) {
      return (
        <li key={i} className="chat-list-item">
          {line.substring(4)}
        </li>
      );
    }

    // Bold paragraph: **bold** rest
    if (line.startsWith('**')) {
      const parts = line.split('**');
      return (
        <p key={i} className="chat-bold-paragraph">
          <strong>{parts[1]}</strong>
          {parts.slice(2).join('**')}
        </p>
      );
    }

    // Empty line → spacer
    if (line.trim() === '') {
      return <div key={i} className="chat-spacer" />;
    }

    // Normal paragraph
    return (
      <p key={i} className="chat-paragraph">
        {line}
      </p>
    );
  });
}
