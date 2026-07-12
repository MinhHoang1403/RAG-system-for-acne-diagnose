import { useState, useEffect } from 'react';
import { fetchModels } from '../api/chatApi.js';

function modelId(model) {
  return model.model_id || model.model;
}

function modelLabel(model) {
  return model.display_name || model.label || modelId(model);
}

export default function ModelSelector({ onModelConfigChange }) {
  const [models, setModels] = useState([]);
  const [selectedProvider, setSelectedProvider] = useState(
    () => localStorage.getItem('acneAdvisorSelectedProvider') || 'gemini'
  );
  const [selectedModel, setSelectedModel] = useState(
    () => localStorage.getItem('acneAdvisorSelectedModel') || ''
  );
  const [allowFallback, setAllowFallback] = useState(
    () => localStorage.getItem('acneAdvisorAllowModelFallback') !== 'false'
  );
  const [loading, setLoading] = useState(true);

  // Fetch models from API
  useEffect(() => {
    let isMounted = true;
    fetchModels()
      .then(data => {
        if (isMounted) {
          const catalog = Array.isArray(data.models) ? data.models : [];
          setModels(catalog);
          const storedProvider = localStorage.getItem('acneAdvisorSelectedProvider') || 'gemini';
          const storedModel = localStorage.getItem('acneAdvisorSelectedModel') || '';
          const selectedKey = `${storedProvider}|${storedModel}`;
          const current = catalog.find((m) => `${m.provider}|${modelId(m)}` === selectedKey && m.available);
          if (!current) {
            const defaultModel = catalog.find(
              (m) => m.provider === data.default_provider && modelId(m) === (data.default_model_id || data.default_model)
            ) || catalog.find((m) => m.is_default) || catalog.find((m) => m.available);
            if (defaultModel) {
              setSelectedProvider(defaultModel.provider);
              setSelectedModel(modelId(defaultModel));
            }
          }
          setLoading(false);
        }
      })
      .catch(err => {
        console.error('Failed to fetch models:', err);
        if (isMounted) setLoading(false);
      });
    return () => { isMounted = false; };
  }, []);

  // Sync state upward and to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('acneAdvisorSelectedProvider', selectedProvider);
    localStorage.setItem('acneAdvisorSelectedModel', selectedModel);
    localStorage.setItem('acneAdvisorAllowModelFallback', allowFallback);

    if (onModelConfigChange) {
      onModelConfigChange({
        llmProvider: selectedProvider,
        llmModel: selectedModel,
        allowModelFallback: allowFallback
      });
    }
  }, [selectedProvider, selectedModel, allowFallback, onModelConfigChange]);

  const handleModelChange = (e) => {
    const val = e.target.value;
    const selectedOption = models.find(m => `${m.provider}|${modelId(m)}` === val);
    if (selectedOption) {
      setSelectedProvider(selectedOption.provider);
      setSelectedModel(modelId(selectedOption));
    }
  };

  return (
    <div className="model-selector-container">
      <select
        value={`${selectedProvider}|${selectedModel}`}
        onChange={handleModelChange}
        disabled={loading}
        className="model-selector-dropdown"
      >
        {loading && <option>Đang tải model...</option>}
        {!loading && models.length === 0 && <option>Không có model khả dụng</option>}
        {!loading && models.map(m => (
          <option
            key={`${m.provider}|${modelId(m)}`}
            value={`${m.provider}|${modelId(m)}`}
            disabled={!m.available}
          >
            {modelLabel(m)} {!m.available ? '(Offline)' : ''}
          </option>
        ))}
      </select>
      
      <label className="model-fallback-toggle" title="Tự động fallback khi lỗi">
        <input
          type="checkbox"
          checked={allowFallback}
          onChange={(e) => setAllowFallback(e.target.checked)}
        />
        Auto fallback
      </label>
    </div>
  );
}
