import React from 'react';

export default function Header({ statusInfo, activeTab, onTabChange, telemetryCount }) {
  return (
    <header className="aepp-header">
      <div className="header-brand">
        <div className="brand-logo">
          <span className="logo-icon">⚡</span>
          <div className="brand-text">
            <h1 className="brand-title">AEPP</h1>
            <span className="brand-subtitle">Agentic Explainable Planning Platform</span>
          </div>
        </div>
      </div>

      <div className="header-center">
        <nav className="nav-tabs">
          <button
            className={`nav-tab ${activeTab === 'studio' ? 'active' : ''}`}
            onClick={() => onTabChange('studio')}
          >
            <span className="tab-icon">🎯</span>
            <span>Planning Studio</span>
          </button>
          <button
            className={`nav-tab ${activeTab === 'telemetry' ? 'active' : ''}`}
            onClick={() => onTabChange('telemetry')}
          >
            <span className="tab-icon">📊</span>
            <span>Telemetry & History</span>
            {telemetryCount > 0 && (
              <span className="tab-badge">{telemetryCount}</span>
            )}
          </button>
        </nav>
      </div>

      <div className="header-status">
        <div className="status-pill" title={statusInfo?.fast_downward ? `Path: ${statusInfo?.fast_downward_path}` : 'Fast Downward binary not found; using Pyperplan pure-Python engine'}>
          <span className={`status-dot ${statusInfo?.fast_downward ? 'green' : 'amber'}`}></span>
          <span className="status-label">
            {statusInfo?.fast_downward ? 'Fast Downward' : 'Pyperplan (Active)'}
          </span>
        </div>

        <div className="status-pill" title={statusInfo?.val_validator ? `VAL binary path: ${statusInfo?.val_path}` : 'VAL binary missing; using internal state-transition validator'}>
          <span className={`status-dot ${statusInfo?.val_validator ? 'green' : 'blue'}`}></span>
          <span className="status-label">
            {statusInfo?.val_validator ? 'VAL Validator' : 'State Transition Validator'}
          </span>
        </div>
      </div>
    </header>
  );
}
