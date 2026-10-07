import React, { useEffect, useMemo, useState } from 'react';
import { SAMPLE_PRESETS } from '../presets';
import { api } from '../api';

export default function InputPanel({
  domainPDDL,
  setDomainPDDL,
  problemPDDL,
  setProblemPDDL,
  onRunPlanning,
  isLoading,
}) {
  const [selectedPresetId, setSelectedPresetId] = useState('blocksworld-sussman');
  const [maxTime, setMaxTime] = useState(60);
  const [forceStrategy, setForceStrategy] = useState('auto');
  const [models, setModels] = useState([]);
  const [modelDefaults, setModelDefaults] = useState({});
  const [selectedModels, setSelectedModels] = useState({});
  const [modelSearch, setModelSearch] = useState('');
  const [modelError, setModelError] = useState(null);
  const [modelsLoading, setModelsLoading] = useState(true);

  useEffect(() => {
    let active = true;
    api.getModels()
      .then((data) => {
        if (!active) return;
        const availableModels = data.models || [];
        const availableIds = new Set(availableModels.map((model) => model.id));
        const availableDefaults = Object.fromEntries(
          Object.entries(data.defaults || {}).filter(([, modelId]) => availableIds.has(modelId)),
        );
        setModels(availableModels);
        setModelDefaults(availableDefaults);
        setSelectedModels(availableDefaults);
      })
      .catch((err) => {
        if (active) setModelError(err.message);
      })
      .finally(() => {
        if (active) setModelsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const filteredModels = useMemo(() => {
    const query = modelSearch.trim().toLowerCase();
    return !query ? models : models.filter((model) => (
      model.id.toLowerCase().includes(query)
      || model.name.toLowerCase().includes(query)
      || model.provider.toLowerCase().includes(query)
    ));
  }, [modelSearch, models]);

  const roleLabels = {
    optimal: 'Optimal Agent',
    satisficing: 'Satisficing Agent',
    agile: 'Agile Agent',
    judge: 'Judge / Chairman',
  };

  const handlePresetSelect = (presetId) => {
    setSelectedPresetId(presetId);
    const preset = SAMPLE_PRESETS.find((p) => p.id === presetId);
    if (preset) {
      setDomainPDDL(preset.domain);
      setProblemPDDL(preset.problem);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!domainPDDL.trim() || !problemPDDL.trim()) return;

    const constraints = {
      max_time: maxTime,
    };
    if (forceStrategy !== 'auto') {
      constraints.force_strategy = forceStrategy;
    }
    if (Object.keys(selectedModels).length === 4) {
      constraints.models = selectedModels;
    }

    onRunPlanning(constraints);
  };

  return (
    <div className="input-panel-card">
      <div className="panel-header">
        <div className="panel-title-group">
          <span className="panel-badge">Step 1</span>
          <h2 className="panel-title">PDDL Problem Specification</h2>
        </div>

        <div className="preset-bar">
          <span className="preset-label">Benchmarks:</span>
          <div className="preset-buttons">
            {SAMPLE_PRESETS.map((preset) => (
              <button
                key={preset.id}
                type="button"
                className={`preset-btn ${selectedPresetId === preset.id ? 'active' : ''}`}
                onClick={() => handlePresetSelect(preset.id)}
                disabled={isLoading}
                title={preset.description}
              >
                {preset.name}
              </button>
            ))}
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="panel-form">
        <div className="editors-grid">
          {/* Domain PDDL Column */}
          <div className="editor-column">
            <div className="editor-header">
              <span className="editor-title">Domain PDDL</span>
              <span className="editor-subtext">(Types, Predicates, Actions)</span>
            </div>

            <div className="model-selection-panel">
              <div className="editor-header">
                <span className="editor-title">Council Models</span>
                <span className="editor-subtext">Separate role selectors with backend override support</span>
              </div>
              <input
                className="model-search-input"
                type="search"
                value={modelSearch}
                onChange={(e) => setModelSearch(e.target.value)}
                placeholder="Search models by name, provider, or ID..."
                disabled={isLoading || modelsLoading}
              />
              {modelsLoading && <p className="model-status">Loading OpenRouter models...</p>}
              {modelError && <p className="model-status model-error">{modelError}</p>}
              {!modelsLoading && !modelError && (
                <div className="model-selectors-grid">
                  {Object.entries(roleLabels).map(([role, label]) => (
                    <label className="control-item" htmlFor={`model-${role}`} key={role}>
                      <span className="control-label">{label}</span>
                      <select
                        id={`model-${role}`}
                        className="control-select"
                        value={selectedModels[role] || modelDefaults[role] || ''}
                        onChange={(e) => setSelectedModels((current) => ({
                          ...current,
                          [role]: e.target.value,
                        }))}
                        disabled={isLoading || modelsLoading}
                      >
                        {[
                          ...(
                            selectedModels[role]
                            && !filteredModels.some((model) => model.id === selectedModels[role])
                            ? models.filter((model) => model.id === selectedModels[role])
                            : []
                          ),
                          ...filteredModels,
                        ].map((model) => (
                          <option value={model.id} key={model.id}>
                            {model.name} ({model.id})
                          </option>
                        ))}
                      </select>
                    </label>
                  ))}
                </div>
              )}
            </div>
            <textarea
              className="pddl-textarea"
              value={domainPDDL}
              onChange={(e) => setDomainPDDL(e.target.value)}
              placeholder="Paste or write your PDDL domain here: (define (domain ...))"
              rows={14}
              spellCheck="false"
              disabled={isLoading}
              required
            />
          </div>

          {/* Problem PDDL Column */}
          <div className="editor-column">
            <div className="editor-header">
              <span className="editor-title">Problem PDDL</span>
              <span className="editor-subtext">(Objects, Initial State, Goal State)</span>
            </div>
            <textarea
              className="pddl-textarea"
              value={problemPDDL}
              onChange={(e) => setProblemPDDL(e.target.value)}
              placeholder="Paste or write your PDDL problem here: (define (problem ...))"
              rows={14}
              spellCheck="false"
              disabled={isLoading}
              required
            />
          </div>
        </div>

        {/* Controls & Action Bar */}
        <div className="panel-footer">
          <div className="controls-group">
            <div className="control-item">
              <label htmlFor="timeout-select" className="control-label">Max CPU Timeout:</label>
              <select
                id="timeout-select"
                className="control-select"
                value={maxTime}
                onChange={(e) => setMaxTime(Number(e.target.value))}
                disabled={isLoading}
              >
                <option value={10}>10 seconds (Strict Agile)</option>
                <option value={30}>30 seconds (Fast)</option>
                <option value={60}>60 seconds (Standard)</option>
                <option value={120}>120 seconds (Deep Search)</option>
                <option value={300}>300 seconds (Comprehensive)</option>
              </select>
            </div>

            <div className="control-item">
              <label htmlFor="strategy-select" className="control-label">Strategy Override:</label>
              <select
                id="strategy-select"
                className="control-select"
                value={forceStrategy}
                onChange={(e) => setForceStrategy(e.target.value)}
                disabled={isLoading}
              >
                <option value="auto">Auto (Council Deliberates)</option>
                <option value="optimal">Force Optimal (A* Search)</option>
                <option value="satisficing">Force Satisficing (LAMA)</option>
                <option value="agile">Force Agile (Fast-Greedy)</option>
              </select>
            </div>
          </div>

          <button
            type="submit"
            className={`run-button ${isLoading ? 'loading' : ''}`}
            disabled={isLoading || !domainPDDL.trim() || !problemPDDL.trim()}
          >
            {isLoading ? (
              <>
                <span className="spinner"></span>
                <span>Council Deliberating & Solving...</span>
              </>
            ) : (
              <>
                <span className="btn-icon">⚡</span>
                <span>Run Council Planning</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}
