import React, { useState } from 'react';

export default function PlanInspector({ plan, cost }) {
  const [copied, setCopied] = useState(false);

  if (!plan || plan.length === 0) {
    return (
      <div className="plan-inspector-card empty">
        <div className="empty-plan-message">
          <span className="empty-plan-icon">📜</span>
          <p>No solution plan generated yet. Run Council Planning to produce a validated plan.</p>
        </div>
      </div>
    );
  }

  const handleCopyPlan = () => {
    const planText = plan.join('\n');
    navigator.clipboard.writeText(planText).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  // Helper to parse "(action arg1 arg2)" into operator and arguments
  const parseActionStep = (actionStr) => {
    const clean = actionStr.trim().replace(/^\(|\)$/g, '');
    const tokens = clean.split(/\s+/);
    const operator = tokens[0] || 'action';
    const args = tokens.slice(1);
    return { operator, args };
  };

  return (
    <div className="plan-inspector-card">
      <div className="plan-header">
        <div className="plan-title-group">
          <span className="panel-badge">Step 5</span>
          <div>
            <h3 className="plan-title">Validated Solution Plan</h3>
            <span className="plan-subtitle">
              Sequential grounded action steps certified by state-transition validation.
            </span>
          </div>
        </div>

        <div className="plan-actions">
          <span className="plan-count-badge">
            Total Steps: <strong>{plan.length}</strong> (Cost: {cost?.toFixed(1) || plan.length})
          </span>
          <button
            type="button"
            className="copy-plan-btn"
            onClick={handleCopyPlan}
          >
            {copied ? '✓ Copied!' : '📋 Copy Plan'}
          </button>
        </div>
      </div>

      <div className="plan-steps-container">
        {plan.map((stepStr, idx) => {
          const { operator, args } = parseActionStep(stepStr);
          const stepNum = String(idx + 1).padStart(2, '0');

          return (
            <div key={idx} className="plan-step-row">
              <span className="step-number">{stepNum}</span>

              <div className="action-pill">
                <span className="action-operator">{operator}</span>
                {args.map((arg, aIdx) => (
                  <span key={aIdx} className="action-arg">
                    {arg}
                  </span>
                ))}
              </div>

              <span className="step-raw-str">{stepStr}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
