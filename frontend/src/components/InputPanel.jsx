import React, { useState } from 'react';
import { SAMPLE_PRESETS } from '../presets';

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
  const [showAdvanced, setShowAdvanced] = useState(false);

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
