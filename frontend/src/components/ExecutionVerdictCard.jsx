import React from 'react';
import ReactMarkdown from 'react-markdown';

export default function ExecutionVerdictCard({
  judgeVerdict,
  execution,
  validation,
  xaiSummary,
}) {
  if (!execution) return null;

  const decision = judgeVerdict?.decision || {};
  const strategy = execution.final_strategy || decision.strategy || 'satisficing';
  const isValid = validation?.valid === true;

  const strategyLabels = {
    optimal: { text: 'OPTIMAL (A* Search)', colorClass: 'badge-optimal' },
    satisficing: { text: 'SATISFICING (LAMA / FF)', colorClass: 'badge-satisficing' },
    agile: { text: 'AGILE (Fast-Greedy)', colorClass: 'badge-agile' },
    mock: { text: 'MOCK (Fallback Emulator)', colorClass: 'badge-mock' },
  };

  const strategyMeta = strategyLabels[strategy.toLowerCase()] || {
    text: strategy.toUpperCase(),
    colorClass: 'badge-default',
  };

  return (
    <div className="verdict-execution-card">
      <div className="section-header">
        <div className="section-title-group">
          <span className="panel-badge">Step 3 & 4</span>
          <h2 className="section-title">Judge Verdict & Classical Execution</h2>
        </div>
      </div>

      {/* Judge Verdict Banner */}
      <div className="judge-verdict-banner">
        <div className="verdict-header">
          <div className="verdict-title-wrap">
            <span className="judge-crown-icon">⚖️</span>
            <div>
              <span className="verdict-meta-title">EXPLAINABLE PLANNING VERDICT</span>
              <h3 className="verdict-strategy-title">
                Selected Strategy: <span className={`strategy-pill ${strategyMeta.colorClass}`}>{strategyMeta.text}</span>
              </h3>
            </div>
          </div>

          <div className="verdict-config-tags">
            {decision.budget_seconds && (
              <span className="config-tag">
                ⏱️ Budget: <strong>{decision.budget_seconds}s</strong>
              </span>
            )}
            {decision.search_configuration && (
              <span className="config-tag">
                ⚙️ Config: <code>{decision.search_configuration}</code>
              </span>
            )}
          </div>
        </div>

        {/* XAI Justification */}
        {(decision.justification_summary || xaiSummary) && (
          <div className="verdict-justification">
            <p className="justification-text">
              <strong>XAI Rationale:</strong> {decision.justification_summary || xaiSummary}
            </p>
          </div>
        )}
      </div>

      {/* Fallback Alert Box (If Triggered) */}
      {execution.fallback_triggered && (
        <div className="fallback-alert-box">
          <div className="fallback-alert-header">
            <span className="fallback-alert-icon">⚠️</span>
            <div className="fallback-alert-content">
              <h4 className="fallback-alert-title">
                Automatic Strategy Fallback Triggered
              </h4>
              <p className="fallback-alert-desc">
                Primary Strategy <strong>'{execution.initial_strategy}'</strong> encountered an operational hurdle (timeout/state space limit).
                The Fallback Manager automatically re-routed and recovered via <strong>'{execution.final_strategy}'</strong>.
              </p>
            </div>
          </div>

          {execution.fallback_history && execution.fallback_history.length > 0 && (
            <div className="fallback-timeline">
              {execution.fallback_history.map((step, idx) => (
                <div key={idx} className="timeline-item">
                  <span className="timeline-step">Attempt {idx + 1}: {step.failed_strategy}</span>
                  <span className="timeline-arrow">➔</span>
                  <span className="timeline-reason">{step.reason}</span>
                </div>
              ))}
              <div className="timeline-item success">
                <span className="timeline-step">Success: {execution.final_strategy}</span>
                <span className="timeline-badge">Recovered</span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Live Execution Metrics Bar */}
      <div className="metrics-dashboard-grid">
        {/* Runtime */}
        <div className="exec-metric-card">
          <span className="exec-metric-label">Solver Runtime</span>
          <div className="exec-metric-main">
            <span className="exec-metric-value">{execution.execution_time?.toFixed(3)}s</span>
            <span className="exec-metric-sub">
              {decision.budget_seconds ? `(Budget: ${decision.budget_seconds}s)` : ''}
            </span>
          </div>
        </div>

        {/* Plan Length */}
        <div className="exec-metric-card">
          <span className="exec-metric-label">Plan Length</span>
          <div className="exec-metric-main">
            <span className="exec-metric-value">{execution.plan?.length || 0}</span>
            <span className="exec-metric-sub">Actions</span>
          </div>
        </div>

        {/* Plan Cost */}
        <div className="exec-metric-card">
          <span className="exec-metric-label">Plan Cost</span>
          <div className="exec-metric-main">
            <span className="exec-metric-value">{validation?.cost?.toFixed(1) || '0.0'}</span>
            <span className="exec-metric-sub">Accumulated Cost</span>
          </div>
        </div>

        {/* Solver Engine */}
        <div className="exec-metric-card">
          <span className="exec-metric-label">Planner Engine</span>
          <div className="exec-metric-main">
            <span className="exec-metric-value capitalize">{execution.planner_used || 'Unknown'}</span>
            <span className="exec-metric-sub">Backend Worker</span>
          </div>
        </div>

        {/* Validation Certificate Badge */}
        <div className={`exec-metric-card validation-card ${isValid ? 'valid' : 'invalid'}`}>
          <span className="exec-metric-label">Validation Status</span>
          <div className="exec-metric-main">
            <span className={`validation-badge ${isValid ? 'badge-valid' : 'badge-invalid'}`}>
              {isValid ? '✓ VALID PLAN' : '✕ INVALID PLAN'}
            </span>
            <span className="exec-metric-sub">
              {isValid ? 'State-transition certified' : validation?.error || 'Validation error'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
