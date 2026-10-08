import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import InputPanel from './components/InputPanel';
import StructuralMetricsPill from './components/StructuralMetricsPill';
import CouncilReview from './components/CouncilReview';
import ExecutionVerdictCard from './components/ExecutionVerdictCard';
import PlanInspector from './components/PlanInspector';
import TelemetryDrawer from './components/TelemetryDrawer';
import { SAMPLE_PRESETS } from './presets';
import { api } from './api';
import './App.css';

export default function App() {
  const [activeTab, setActiveTab] = useState('studio');
  const [domainPDDL, setDomainPDDL] = useState(SAMPLE_PRESETS[0].domain);
  const [problemPDDL, setProblemPDDL] = useState(SAMPLE_PRESETS[0].problem);

  const [isLoading, setIsLoading] = useState(false);
  const [statusInfo, setStatusInfo] = useState(null);
  const [planningResult, setPlanningResult] = useState(null);
  const [telemetryCount, setTelemetryCount] = useState(0);
  const [errorMessage, setErrorMessage] = useState(null);
  const [planningStep, setPlanningStep] = useState(0);
  const [liveStepDetail, setLiveStepDetail] = useState(null);
  const [planningElapsedSeconds, setPlanningElapsedSeconds] = useState(0);

  const planningSteps = [
    {
      title: 'Checking your PDDL problem',
      detail: 'Reading the domain, objects, actions, and goals.',
    },
    {
      title: 'Preparing the council',
      detail: 'Loading the selected OpenRouter models and planning context.',
    },
    {
      title: 'Collecting strategy proposals',
      detail: 'Optimal, satisficing, and agile agents are analyzing the problem.',
    },
    {
      title: 'Running anonymous peer review',
      detail: 'Council agents are comparing and ranking the proposals.',
    },
    {
      title: 'Judge is synthesizing a decision',
      detail: 'The chairman is selecting a planning strategy and time budget.',
    },
    {
      title: 'Executing and validating the plan',
      detail: 'The classical planner is searching, then checking every action.',
    },
    {
      title: 'Finalizing the explanation',
      detail: 'Packaging the plan, debate, validation, and telemetry results.',
    },
  ];

  useEffect(() => {
    if (!isLoading) return undefined;

    const elapsedIntervalId = window.setInterval(() => {
      setPlanningElapsedSeconds((seconds) => seconds + 1);
    }, 1000);

    return () => {
      window.clearInterval(elapsedIntervalId);
    };
  }, [isLoading]);

  useEffect(() => {
    loadInitialStatus();
  }, []);

  const loadInitialStatus = async () => {
    try {
      const status = await api.getPDDLStatus();
      setStatusInfo(status);
    } catch (err) {
      console.warn('Backend status check pending:', err);
    }

    try {
      const telem = await api.getTelemetry(1);
      setTelemetryCount(telem.count || 0);
    } catch (err) {
      console.warn('Telemetry fetch pending:', err);
    }
  };

  const handleRunPlanning = async (constraints) => {
    setIsLoading(true);
    setPlanningStep(0);
    setLiveStepDetail(null);
    setPlanningElapsedSeconds(0);
    setErrorMessage(null);

    try {
      await api.solvePDDLStream(
        domainPDDL,
        problemPDDL,
        constraints,
        (stepIndex, detail) => {
          setPlanningStep(stepIndex);
          if (detail) setLiveStepDetail(detail);
        },
        (result) => {
          setPlanningResult(result);
          setTelemetryCount((prev) => prev + 1);

          // Scroll smoothly down to results
          setTimeout(() => {
            const resultsEl = document.getElementById('planning-results-anchor');
            if (resultsEl) {
              resultsEl.scrollIntoView({ behavior: 'smooth' });
            }
          }, 100);
        },
        (err) => {
          console.error('Planning pipeline error:', err);
          setErrorMessage(err.message || 'An error occurred during planning deliberation.');
        }
      );
    } catch (err) {
      console.error('Streaming connection error:', err);
      setErrorMessage(err.message || 'An error occurred during planning deliberation.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="aepp-app-root">
      <Header
        statusInfo={statusInfo}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        telemetryCount={telemetryCount}
      />

      <main className="aepp-main-content">
        {activeTab === 'studio' ? (
          <div className="studio-workspace">
            {/* Input Panel */}
            <InputPanel
              domainPDDL={domainPDDL}
              setDomainPDDL={setDomainPDDL}
              problemPDDL={problemPDDL}
              setProblemPDDL={setProblemPDDL}
              onRunPlanning={handleRunPlanning}
              isLoading={isLoading}
            />

            {isLoading && (
              <section className="planning-progress-panel" aria-live="polite" aria-label="Planning progress">
                <div className="planning-progress-header">
                  <div>
                    <p className="planning-progress-eyebrow">Council planning in progress</p>
                    <h2>{planningSteps[planningStep].title}</h2>
                    <p>{liveStepDetail || planningSteps[planningStep].detail}</p>
                  </div>
                  <div className="planning-progress-status">
                    <span className="progress-spinner" aria-hidden="true" />
                    <strong>Working</strong>
                    <span>{planningElapsedSeconds}s elapsed</span>
                  </div>
                </div>
                <ol className="planning-progress-steps">
                  {planningSteps.map((step, index) => (
                    <li
                      className={index < planningStep ? 'complete' : index === planningStep ? 'active' : ''}
                      key={step.title}
                    >
                      <span className="planning-step-marker" aria-hidden="true">
                        {index < planningStep ? '✓' : index + 1}
                      </span>
                      <span>{step.title}</span>
                    </li>
                  ))}
                </ol>
                <p className="planning-progress-note">
                  This may take a little while because several agents and the planner are working in sequence.
                </p>
              </section>
            )}

            {/* Error Notification */}
            {errorMessage && (
              <div className="pipeline-error-banner">
                <span className="error-icon">⚠️</span>
                <div className="error-content">
                  <h4>Planning Pipeline Execution Issue</h4>
                  <p>{errorMessage}</p>
                </div>
                <button className="error-dismiss" onClick={() => setErrorMessage(null)}>✕</button>
              </div>
            )}

            {/* Planning Results Anchor */}
            <div id="planning-results-anchor" />

            {/* Planning Results Display */}
            {planningResult && (
              <div className="results-container">
                {/* Structural Analysis Header */}
                <StructuralMetricsPill metrics={planningResult.metrics} />

                {/* Step 2: 3-Way Council Review & Peer Critique */}
                <CouncilReview debate={planningResult.debate} />

                {/* Step 3 & 4: Judge Verdict Banner & Live Metrics */}
                <ExecutionVerdictCard
                  judgeVerdict={planningResult.debate?.judge_verdict}
                  execution={planningResult.execution}
                  validation={planningResult.validation}
                  xaiSummary={planningResult.xai_summary}
                />

                {/* Step 5: Sequential Solution Plan Inspector */}
                <PlanInspector
                  plan={planningResult.execution?.plan}
                  cost={planningResult.validation?.cost}
                />
              </div>
            )}
          </div>
        ) : (
          <div className="telemetry-workspace">
            <TelemetryDrawer />
          </div>
        )}
      </main>
    </div>
  );
}
