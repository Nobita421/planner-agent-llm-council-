import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';

export default function CouncilReview({ debate }) {
  const [activeReviewTab, setActiveReviewTab] = useState(0);

  if (!debate || !debate.stage1) return null;

  const stage1 = debate.stage1 || [];
  const stage2 = debate.stage2 || [];
  const aggregateRankings = debate.aggregate_rankings || [];

  // Map roles to distinct styling themes
  const roleThemes = {
    optimal: {
      colorClass: 'theme-optimal',
      badgeText: 'A* Admissibility Specialist',
      icon: '🛡️',
      accentColor: '#10b981',
    },
    satisficing: {
      colorClass: 'theme-satisficing',
      badgeText: 'LAMA Heuristic Specialist',
      icon: '⚖️',
      accentColor: '#8b5cf6',
    },
    agile: {
      colorClass: 'theme-agile',
      badgeText: 'Fast-Greedy Specialist',
      icon: '🚀',
      accentColor: '#f59e0b',
    },
  };

  return (
    <div className="council-review-section">
      <div className="section-header">
        <div className="section-title-group">
          <span className="panel-badge">Step 2</span>
          <h2 className="section-title">Council Deliberation & Peer Review</h2>
        </div>
        <span className="section-subtitle">
          Specialized planning agents debate state space feasibility, combinatorial risk, and timeouts.
        </span>
      </div>

      {/* 3-Way Side-by-Side Comparison Grid */}
      <div className="agents-triptych">
        {stage1.map((agent) => {
          const theme = roleThemes[agent.role] || {
            colorClass: 'theme-default',
            badgeText: 'Planning Specialist',
            icon: '🤖',
          };

          return (
            <div key={agent.role} className={`agent-card ${theme.colorClass}`}>
              <div className="agent-card-header">
                <div className="agent-avatar-group">
                  <span className="agent-icon">{theme.icon}</span>
                  <div>
                    <h3 className="agent-name">{agent.agent_name || agent.role}</h3>
                    <span className="agent-badge">{theme.badgeText}</span>
                  </div>
                </div>
                <span className="agent-model-tag">{agent.model}</span>
              </div>

              <div className="agent-argument-content markdown-content">
                <ReactMarkdown>{agent.response}</ReactMarkdown>
              </div>
            </div>
          );
        })}
      </div>

      {/* Stage 2: Peer Critique & Consensus Section */}
      {stage2.length > 0 && (
        <div className="peer-critique-card">
          <div className="critique-header">
            <div className="critique-title-group">
              <span className="critique-icon">🔍</span>
              <div>
                <h3 className="critique-title">Peer Critique & Consensus Analysis</h3>
                <span className="critique-subtitle">
                  Agents critically analyze peer proposals for risk of combinatorial state space explosion vs optimality need.
                </span>
              </div>
            </div>

            {/* Aggregate Rankings Summary */}
            {aggregateRankings.length > 0 && (
              <div className="consensus-summary">
                <span className="consensus-title">Consensus Ranking:</span>
                <div className="rank-chips">
                  {aggregateRankings.map((rank, idx) => (
                    <span key={rank.model} className="rank-chip">
                      #{idx + 1} {rank.model.split('/').pop()} (avg {rank.average_rank})
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Reviewer Tabs */}
          <div className="critique-tabs">
            {stage2.map((review, idx) => (
              <button
                key={review.role || idx}
                className={`critique-tab ${activeReviewTab === idx ? 'active' : ''}`}
                onClick={() => setActiveReviewTab(idx)}
              >
                <span>{review.agent_name || `Agent ${idx + 1}`}</span>
              </button>
            ))}
          </div>

          <div className="critique-body markdown-content">
            {stage2[activeReviewTab] && (
              <ReactMarkdown>{stage2[activeReviewTab].ranking}</ReactMarkdown>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
