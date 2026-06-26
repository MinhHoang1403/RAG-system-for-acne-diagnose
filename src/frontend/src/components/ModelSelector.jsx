import React, { useState, useEffect } from 'react';
import { fetchModels } from '../api/chatApi.js';

export default function ModelSelector({ onModelConfigChange }) {
  const [models, setModels] = useState([]);
  const [selectedProvider, setSelectedProvider] = useState('gemini');
  const [selectedModel, setSelectedModel] = useState('gemini-2.5-flash');
  const [allowFallback, setAllowFallback] = useState(true);
  const [loading, setLoading] = useState(true);

  // Read from localStorage on mount
  useEffect(() => {
    const savedProvider = localStorage.getItem('acneAdvisorSelectedProvider');
    const savedModel = localStorage.getItem('acneAdvisorSelectedModel');
    const savedFallback = localStorage.getItem('acneAdvisorAllowModelFallback');

    if (savedProvider) setSelectedProvider(savedProvider);
    if (savedModel) setSelectedModel(savedModel);
    if (savedFallback !== null) setAllowFallback(savedFallback === 'true');
  }, []);

  // Fetch models from API
  useEffect(() => {
    let isMounted = true;
    fetchModels()
      .then(data => {
        if (isMounted) {
          setModels(data.models);
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
    const selectedOption = models.find(m => `${m.provider}|${m.model}` === val);
    if (selectedOption) {
      setSelectedProvider(selectedOption.provider);
      setSelectedModel(selectedOption.model);
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
        {!loading && models.map(m => (
          <option 
            key={`${m.provider}|${m.model}`} 
            value={`${m.provider}|${m.model}`}
            disabled={!m.available}
          >
            {m.label} {!m.available ? '(Offline)' : ''}
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
