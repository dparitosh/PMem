import React, { useEffect, useRef, useState } from 'react';
import { agenticClient } from '../services/agenticApi';
import { buildSemanticServiceUrl } from '../config';
import { getCredentialProfile } from '../services/serviceAuth';

export default function AgentProposalPanel() {
  const [agents, setAgents] = useState([]), [agent, setAgent] = useState('');
  const [task, setTask] = useState(''), [proposal, setProposal] = useState(null);
  const [actor, setActor] = useState(''), [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const [savedId, setSavedId] = useState(() => { try { return sessionStorage.getItem('depo:agent-recommendation') || ''; } catch { return ''; } });
  const [execution, setExecution] = useState(null);
  const request = useRef(null);
  const reset = () => { request.current?.abort(); setProposal(null); setReviewed(false); setMessage(''); setBusy(false); setExecution(null); };
  useEffect(() => {
    const events = ['depo:credentials-changed', 'depo:credentials-cleared'];
    events.forEach(event => window.addEventListener(event, reset));
    return () => { request.current?.abort(); events.forEach(event => window.removeEventListener(event, reset)); };
  }, []);
  const operate = async action => {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setBusy(true); setMessage(''); setExecution(null);
    try {
      const url = path => buildSemanticServiceUrl('agentic', `/api/v1/${path}`);
      const options = { signal: controller.signal };
      let response;
      if (action === 'load') {
        response = await agenticClient.get(url('agents'), options);
        if (!Array.isArray(response.data.agents)) throw new Error('Invalid agent catalog.');
        if (!controller.signal.aborted) { setAgents(response.data.agents); setAgent(response.data.agents[0]?.id || ''); }
      } else if (action === 'suggest') {
        setProposal(null); setReviewed(false);
        response = await agenticClient.post(url(`agents/${encodeURIComponent(agent)}/suggest`), { task: task.trim() }, options);
        if (!response.data.command || response.data.command.agent_id !== agent || !response.data.command.tool_id || typeof response.data.requires_approval !== 'boolean') throw new Error('Invalid agent proposal.');
        if (!controller.signal.aborted) {
          setProposal(response.data); setSavedId(response.data.recommendation_id || '');
          try { if (response.data.recommendation_id) sessionStorage.setItem('depo:agent-recommendation', response.data.recommendation_id); } catch { /* optional bookmark */ }
        }
      } else if (action === 'reload') {
        response = await agenticClient.get(url(`agent-recommendations/${encodeURIComponent(savedId.trim())}`), options);
        const value = response.data;
        if (!value.command?.agent_id || !value.command?.tool_id || typeof value.requires_approval !== 'boolean') throw new Error('Invalid saved recommendation.');
        if (!controller.signal.aborted) {
          setProposal(value); setReviewed(false); setAgent(value.command.agent_id);
          setAgents(current => current.some(item => item.id === value.command.agent_id) ? current : [...current, {id: value.command.agent_id}]);
        }
      } else {
        if (!proposal || !reviewed) throw new Error('Review the proposal first.');
        const token = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
        if (proposal.requires_approval && (!actor.trim() || !token)) throw new Error('Enter the steward and connect governed access in Admin.');
        const command = proposal.command;
        setProposal(null); setReviewed(false);
        response = await agenticClient.post(url('runs'), { ...command, approved_by: actor.trim(), approval_token: token, wait_for_completion: false }, options);
        if (!controller.signal.aborted) { setMessage(response.data.status === 'queued' ? `Execution queued. Workflow run: ${response.data.run_id}. Inspect its status before retrying.` : `Execution completed. ${response.data.execution_kind === 'workflow' ? 'Workflow' : 'Agent'} run: ${response.data.run_id}`); setExecution(response.data); setProposal(null); setReviewed(false); }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        const runId = error.response?.headers?.get?.('X-DEPO-Run-ID') || error.response?.headers?.['x-depo-run-id'];
        setMessage((typeof error.response?.data?.detail === 'string' ? error.response.data.detail : error.message) +
          (runId ? ` Agent run: ${runId}. Inspect telemetry before retrying a write.` : ''));
      }
    }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  return <section aria-label="Agent recommendations" className="depo-panel depo-agent-recommendations">
    <div className="depo-panel__header"><h3>Agent recommendations</h3></div>
    <div className="depo-panel__body">
    <p>Ask an agent to propose one permitted action. Review its inputs before execution; a recommendation does not grant approval.</p>
    <button disabled={busy} onClick={() => { reset(); operate('load'); }}>Load agents</button>
    <label>Agent <select aria-label="Recommendation agent" disabled={busy || !agents.length} value={agent} onChange={event => { reset(); setAgent(event.target.value); }}>{!agents.length && <option value="">Load agents to select an agent</option>}{agents.map(item => <option key={item.id} value={item.id}>{item.name || item.id}</option>)}</select></label>
    {agent && <p>{agents.find(item => item.id === agent)?.description} {agents.find(item => item.id === agent)?.registration_status}</p>}
    <label>Task <textarea aria-label="Recommendation task" maxLength={8000} disabled={busy} value={task} onChange={event => { reset(); setTask(event.target.value); }} /></label>
    <button disabled={busy || !agent || !task.trim()} onClick={() => operate('suggest')}>Get recommendation</button>
    <label>Saved recommendation ID <input aria-label="Saved recommendation ID" value={savedId} disabled={busy} onChange={event => { reset(); setSavedId(event.target.value); }} /></label>
    <button disabled={busy || !savedId.trim()} onClick={() => { setProposal(null); setReviewed(false); operate('reload'); }}>Load saved recommendation</button>
    {proposal && <div><strong>Proposed tool: {proposal.command.tool_id}</strong><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(proposal.command.inputs, null, 2)}</pre>
      <label>Steward <input aria-label="Recommendation steward" value={actor} disabled={busy} onChange={event => { setActor(event.target.value); setReviewed(false); }} /></label>
      <label><input type="checkbox" checked={reviewed} disabled={busy} onChange={event => setReviewed(event.target.checked)} />I reviewed the proposed action and inputs</label>
      <button disabled={busy || !reviewed || (proposal.requires_approval && !actor.trim())} onClick={() => operate('execute')}>Execute reviewed recommendation</button>
    </div>}
    {busy && <><button onClick={reset}>Stop waiting</button><p>Stopping the wait does not undo an execution. Inspect agent telemetry before retrying a write.</p></>}
    {message && <p role="status">{message}</p>}
    {execution && <><button onClick={() => window.dispatchEvent(new CustomEvent('depo:inspect-agent-run', {detail:execution}))}>{execution.execution_kind === 'workflow' ? 'Inspect workflow execution' : 'Inspect standalone execution'}</button><details open><summary>Execution result</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(execution.result, null, 2)}</pre></details></>}
    </div>
  </section>;
}
