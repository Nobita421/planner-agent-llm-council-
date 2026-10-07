import React, { useState, useEffect } from 'react';
import { api } from '../api';

export default function TelemetryDrawer({ onSelectRecord }) {
  const [records, setRecords] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [filterProblem, setFilterProblem] = useState('');

  useEffect(() => {
    loadTelemetry();
  }, []);

  const loadTelemetry = async () => {
    setIsLoading(true);
    try {
      const data = await api.getTelemetry(100);
      setRecords(data.records || []);
    } catch (err) {
      console.error('Failed to load telemetry:', err);
    } finally {
      setIsLoading(false);
    }
  };

  // Compute aggregate statistics
  const totalRuns = records.length;
  const validRuns = records.filter((r) => r.validity).length;
  const successRate = totalRuns > 0 ? Math.round((validRuns / totalRuns) * 100) : 100;
  const avgTime = totalRuns > 0 ? (records.reduce((acc, r) => acc + (r.actual_time || 0), 0) / totalRuns).toFixed(3) : '0.000';

  const strategyCounts = records.reduce((acc, r) => {
    const prof = r.chosen_profile || 'unknown';
    acc[prof] = (acc[prof] || 0) + 1;
    return acc;
  }, {});

  const filteredRecords = filterProblem
    ? records.filter((r) => r.problem_name.toLowerCase().includes(filterProblem.toLowerCase()))
    : records;

  return (
    <div className="telemetry-view-container">
      <div className="telemetry-header">
        <div>
          <h2 className="telemetry-title">Planning Telemetry & Historical Analytics</h2>
          <p className="telemetry-subtitle">
            Persistent execution metrics and judge selection performance tracked in SQLite (telemetry.db).
          </p>
        </div>
        <button
          className="refresh-btn"
          onClick={loadTelemetry}
          disabled={isLoading}
        >
          {isLoading ? 'Refreshing...' : '🔄 Refresh Log'}
        </button>
      </div>

      {/* Aggregate Stats Cards */}
      <div className="telemetry-stats-grid">
        <div className="stat-card">
          <span className="stat-card-label">Total Deliberations</span>
          <span className="stat-card-value">{totalRuns}</span>
          <span className="stat-card-sub">Recorded planning episodes</span>
        </div>

        <div className="stat-card">
          <span className="stat-card-label">Validation Success Rate</span>
          <span className="stat-card-value text-emerald">{successRate}%</span>
          <span className="stat-card-sub">{validRuns} of {totalRuns} certified valid</span>
        </div>

        <div className="stat-card">
          <span className="stat-card-label">Avg Execution Time</span>
          <span className="stat-card-value">{avgTime}s</span>
          <span className="stat-card-sub">End-to-end planning latency</span>
        </div>

        <div className="stat-card">
          <span className="stat-card-label">Strategy Distribution</span>
          <div className="strategy-distribution-list">
            {Object.entries(strategyCounts).map(([strat, count]) => (
              <span key={strat} className="strat-count-pill">
                {strat}: <strong>{count}</strong>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Filter and Table */}
      <div className="telemetry-table-card">
        <div className="table-controls">
          <input
            type="text"
            className="filter-input"
            placeholder="Filter by problem name..."
            value={filterProblem}
            onChange={(e) => setFilterProblem(e.target.value)}
          />
          <span className="filter-count">Showing {filteredRecords.length} records</span>
        </div>

        <div className="table-wrapper">
          <table className="telemetry-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Timestamp</th>
                <th>Problem</th>
                <th>Strategy</th>
                <th>Runtime</th>
                <th>Steps</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredRecords.length === 0 ? (
                <tr>
                  <td colSpan={8} className="empty-row">
                    No telemetry records found.
                  </td>
                </tr>
              ) : (
                filteredRecords.map((rec) => (
                  <tr key={rec.id} className={selectedRecord?.id === rec.id ? 'row-selected' : ''}>
                    <td className="font-mono">#{rec.id}</td>
                    <td className="text-muted">{rec.timestamp || 'Recent'}</td>
                    <td className="font-bold">{rec.problem_name}</td>
                    <td>
                      <span className={`profile-tag ${rec.chosen_profile?.includes('->') ? 'fallback' : ''}`}>
                        {rec.chosen_profile}
                      </span>
                    </td>
                    <td>{rec.actual_time?.toFixed(3)}s</td>
                    <td>{rec.plan_length}</td>
                    <td>
                      <span className={`status-pill-small ${rec.validity ? 'valid' : 'invalid'}`}>
                        {rec.validity ? '✓ VALID' : '✕ FAIL'}
                      </span>
                    </td>
                    <td>
                      <button
                        className="view-detail-btn"
                        onClick={() => setSelectedRecord(rec)}
                      >
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Detail Modal/Drawer */}
      {selectedRecord && (
        <div className="record-modal-overlay" onClick={() => setSelectedRecord(null)}>
          <div className="record-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Telemetry Inspection: #{selectedRecord.id} — {selectedRecord.problem_name}</h3>
              <button className="close-btn" onClick={() => setSelectedRecord(null)}>✕</button>
            </div>

            <div className="modal-body">
              <div className="modal-meta-grid">
                <div>
                  <span className="meta-label">Strategy Chosen:</span>
                  <span className="meta-val">{selectedRecord.chosen_profile}</span>
                </div>
                <div>
                  <span className="meta-label">Actual Time / Budget:</span>
                  <span className="meta-val">{selectedRecord.actual_time}s / {selectedRecord.predicted_budget}s</span>
                </div>
                <div>
                  <span className="meta-label">Plan Cost & Length:</span>
                  <span className="meta-val">{selectedRecord.cost} cost ({selectedRecord.plan_length} actions)</span>
                </div>
                <div>
                  <span className="meta-label">Validity:</span>
                  <span className={`status-pill-small ${selectedRecord.validity ? 'valid' : 'invalid'}`}>
                    {selectedRecord.validity ? 'Valid Plan' : 'Invalid / Failed'}
                  </span>
                </div>
              </div>

              <div className="modal-section">
                <h4>Judge XAI Rationale</h4>
                <p className="modal-rationale">{selectedRecord.judge_rationale}</p>
              </div>

              {selectedRecord.plan && selectedRecord.plan.length > 0 && (
                <div className="modal-section">
                  <h4>Recorded Plan ({selectedRecord.plan.length} Steps)</h4>
                  <pre className="modal-plan-pre">
                    {selectedRecord.plan.join('\n')}
                  </pre>
                </div>
              )}

              {selectedRecord.error && (
                <div className="modal-section error-section">
                  <h4>Error Details</h4>
                  <pre className="modal-error-pre">{selectedRecord.error}</pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
