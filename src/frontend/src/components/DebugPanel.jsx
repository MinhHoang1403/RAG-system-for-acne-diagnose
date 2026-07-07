export default function DebugPanel({ graphFacts }) {
  if (!graphFacts || graphFacts.length === 0) return null;

  return (
    <details className="debug-panel">
      <summary className="debug-panel-summary">
        <svg
          className="debug-panel-chevron"
          width="16"
          height="16"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
        </svg>
        Dữ liệu kỹ thuật / Debug ({graphFacts.length})
      </summary>
      <div className="debug-panel-content">
        <p className="debug-panel-disclaimer">
          * Phần này dùng để kiểm tra truy xuất tri thức, không phải hướng dẫn điều trị.
        </p>
        <div className="debug-facts-list">
          {graphFacts.map((fact, i) => (
            <div key={i} className="debug-fact">
              <span className="debug-fact-entity">{fact.entity}</span>
              <span className="debug-fact-relationship">-[{fact.relationship}]-&gt;</span>
              <span className="debug-fact-related">{fact.related_entity}</span>
              {fact.description && (
                <div className="debug-fact-description">&quot;{fact.description}&quot;</div>
              )}
            </div>
          ))}
        </div>
      </div>
    </details>
  );
}
