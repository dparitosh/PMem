import React from 'react';
import TaskProgress from './TaskProgress';
import useReadGoal from '../features/agents/hooks/useReadGoal';

export default function ReadGoalPanel({ agent, task, context, storageKey, initialRunId = '', resumeOnly = false, compact = false, disabled = false, startLabel = 'Start read-only investigation', onRunChange }) {
  const { run, error, busy, pending, runId, active, start, cancel, close } = useReadGoal({ agent, task, context, storageKey, initialRunId, onRunChange });
  return <section aria-label="Read-only goal investigation" className={compact?'read-goal-compact':'depo-panel'}>
    {!compact&&<><h4>Investigate a goal with the agent</h4>
    <p>The agent uses the configured model to plan subtasks, uses registered read tools, and revises its approach after a failed read. The plan and observations are retained in PostgreSQL across restarts. This mode cannot publish or modify the knowledge graph.</p></>}
    {!resumeOnly && <button type="button" disabled={disabled || busy || active || !agent || !task?.trim()} onClick={start}>{busy ? 'Starting investigation…' : pending ? 'Recover submitted investigation' : startLabel}</button>}
    {runId && <button type="button" onClick={close}>Close investigation view (task is retained)</button>}
    {active && <button type="button" disabled={busy} onClick={cancel}>Cancel investigation</button>}
    {error && <p role="alert">{error}</p>}
    {run && <TaskProgress run={run} kind="goal" />}

  </section>;
}
