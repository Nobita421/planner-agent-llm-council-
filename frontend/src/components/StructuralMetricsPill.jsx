import React from 'react';

export default function StructuralMetricsPill({ metrics }) {
  if (!metrics) return null;

  return (
    <div className="metrics-banner">
      <div className="metrics-header">
        <span className="metrics-badge">PDDL Analysis</span>
        <h3 className="metrics-title">
          {metrics.domain_name} / {metrics.problem_name}
        </h3>
      </div>

      <div className="metrics-grid">
        <div className="metric-chip">
          <span className="metric-chip-label">Objects</span>
          <span className="metric-chip-value">{metrics.objects_count}</span>
        </div>

        <div className="metric-chip">
          <span className="metric-chip-label">Predicates</span>
          <span className="metric-chip-value">{metrics.predicates_count}</span>
        </div>

        <div className="metric-chip">
          <span className="metric-chip-label">Actions</span>
          <span className="metric-chip-value">{metrics.actions_count}</span>
        </div>

        <div className="metric-chip">
          <span className="metric-chip-label">Goals</span>
          <span className="metric-chip-value">{metrics.goals_count}</span>
        </div>

        <div className="metric-chip">
          <span className="metric-chip-label">Action Costs</span>
          <span className={`metric-chip-value ${metrics.has_action_costs ? 'amber' : ''}`}>
            {metrics.has_action_costs ? 'Yes' : 'No'}
          </span>
        </div>

        <div className="metric-chip">
          <span className="metric-chip-label">Numeric</span>
          <span className={`metric-chip-value ${metrics.has_numeric_fluents ? 'amber' : ''}`}>
            {metrics.has_numeric_fluents ? 'Yes' : 'No'}
          </span>
        </div>

        <div className="metric-chip">
          <span className="metric-chip-label">Typing</span>
          <span className="metric-chip-value">
            {metrics.has_typing ? 'Yes' : 'No'}
          </span>
        </div>
      </div>
    </div>
  );
}
