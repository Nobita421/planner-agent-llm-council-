import React, { useEffect, useState } from 'react';
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
  const [roleSearches, setRoleSearches] = useState({});
  const [openRole, setOpenRole] = useState(null);
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

  const roleLabels = {
    optimal: 'Optimal Agent',
    satisficing: 'Satisficing Agent',
    agile: 'Agile Agent',
    judge: 'Judge / Chairman',
  };

  const resetModels = () => {
    setSelectedModels(modelDefaults);
    setOpenRole(null);
  };

  const getRoleModels = (role) => {
    const query = (roleSearches[role] || '').trim().toLowerCase();
    const matchingModels = !query ? models : models.filter((model) => (
      model.id.toLowerCase().includes(query)
      || model.name.toLowerCase().includes(query)
      || model.provider.toLowerCase().includes(query)
    ));
    const selectedModelId = selectedModels[role] || modelDefaults[role] || '';
    if (selectedModelId && !matchingModels.some((model) => model.id === selectedModelId)) {
      return [
        ...models.filter((model) => model.id === selectedModelId),
        ...matchingModels,
      ];
    }
    return matchingModels;
  };

  const getMatchingModelCount = (role) => {
    const query = (roleSearches[role] || '').trim().toLowerCase();
    if (!query) return models.length;
    return models.filter((model) => (
      model.id.toLowerCase().includes(query)
      || model.name.toLowerCase().includes(query)
      || model.provider.toLowerCase().includes(query)
    )).length;
  };

  const getModelPricingLabel = (model) => {
    const promptPrice = Number(model.pricing?.prompt);
    const completionPrice = Number(model.pricing?.completion);
    return promptPrice === 0 && completionPrice === 0 ? 'Free' : 'Paid';
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
    const activeModels = {
      optimal: selectedModels.optimal || modelDefaults.optimal,
      satisficing: selectedModels.satisficing || modelDefaults.satisficing,
      agile: selectedModels.agile || modelDefaults.agile,
      judge: selectedModels.judge || modelDefaults.judge,
    };
    // Include models if any role is configured
    if (activeModels.optimal && activeModels.satisficing && activeModels.agile && activeModels.judge) {
      constraints.models = activeModels;
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

        <div className="model-selection-panel">
          <div className="model-panel-header">
            <div className="editor-header">
              <span className="editor-title">Council Models</span>
              <span className="editor-subtext">Separate role selectors with backend override support</span>
            </div>
            {!modelsLoading && !modelError && (
              <button type="button" className="model-reset-button" onClick={resetModels} disabled={isLoading}>
                Reset defaults
              </button>
            )}
          </div>
          {modelsLoading && <p className="model-status">Loading OpenRouter models...</p>}
          {modelError && <p className="model-status model-error">{modelError}</p>}
          {!modelsLoading && !modelError && (
            <div className="model-selectors-grid">
              {Object.entries(roleLabels).map(([role, label]) => {
                const selectedModelId = selectedModels[role] || modelDefaults[role] || '';
                const selectedModel = models.find((model) => model.id === selectedModelId);
                const roleModels = getRoleModels(role);
                const isOpen = openRole === role;
                return (
                  <div className={`model-role-picker ${isOpen ? 'open' : ''}`} key={role}>
                    <span className="control-label">{label}</span>
                    <button
                      type="button"
                      className="model-picker-trigger"
                      aria-expanded={isOpen}
                      aria-controls={`model-options-${role}`}
                      onClick={() => setOpenRole(isOpen ? null : role)}
                      disabled={isLoading || modelsLoading}
                    >
                      <span className="model-picker-selected">
                        <strong>{selectedModel?.name || selectedModelId || 'No model selected'}</strong>
                        <small>{selectedModelId}</small>
                      </span>
                      <span aria-hidden="true" className="model-picker-chevron">{isOpen ? '▴' : '▾'}</span>
                    </button>
                    {isOpen && (
                      <div className="model-options" id={`model-options-${role}`}>
                        <input
                          className="model-role-search"
                          type="search"
                          value={roleSearches[role] || ''}
                          onChange={(e) => setRoleSearches((current) => ({
                            ...current,
                            [role]: e.target.value,
                          }))}
                          placeholder={`Search ${label} models...`}
                          aria-label={`Search ${label} models`}
                          autoFocus
                        />
                        <span className="model-result-count">
                          {getMatchingModelCount(role) === 0
                            ? 'No other models match; showing the selected model'
                            : `${getMatchingModelCount(role)} matching models`}
                        </span>
                        <div className="model-options-list">
                          {roleModels.length === 0 ? (
                            <p className="model-status">No models match this search.</p>
                          ) : roleModels.map((model) => (
                            <button
                              type="button"
                              className={`model-option-card ${model.id === selectedModelId ? 'selected' : ''}`}
                              key={model.id}
                              onClick={() => {
                                setSelectedModels((current) => ({ ...current, [role]: model.id }));
                                setOpenRole(null);
                              }}
                            >
                              <span className="model-option-main">
                                <strong>{model.name}</strong>
                                <small>{model.provider || 'Unknown provider'}</small>
                              </span>
                              <span className="model-option-meta">
                                <small>{model.id}</small>
                                <em>{getModelPricingLabel(model)}</em>
                              </span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
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
