import React, { useEffect, useRef, useState } from 'react';
import { agenticClient } from '../services/agenticApi';
import { buildSemanticServiceUrl } from '../config';
import { getCredentialProfile } from '../services/serviceAuth';
import { Bot, ListChecks, MessageSquare, ShieldCheck } from 'lucide-react';

const contextIdentity = value => JSON.stringify(value, (key, item) => item && typeof item === 'object' && !Array.isArray(item)
  ? Object.fromEntries(Object.keys(item).sort().map(name => [name, item[name]])) : item);
const validProposal = value => value && value.command && typeof value.command.agent_id === 'string' && typeof value.command.tool_id === 'string' &&
  value.command.inputs && typeof value.command.inputs === 'object' && !Array.isArray(value.command.inputs) && typeof value.requires_approval === 'boolean' &&
  (!value.prompt_details || (typeof value.prompt_details === 'object' && ['model', 'prompt_version', 'user_request', 'system_prompt', 'user_prompt'].every(key => value.prompt_details[key] === undefined || typeof value.prompt_details[key] === 'string')));

export default function AgentProposalPanel({ agentIds, context = null, title = 'Agent recommendations' }) {
  const [agents, setAgents] = useState([]), [agent, setAgent] = useState('');
  const [task, setTask] = useState(''), [proposal, setProposal] = useState(null);
  const [actor, setActor] = useState(''), [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const [savedId, setSavedId] = useState(() => { try { return sessionStorage.getItem('depo:agent-recommendation') || ''; } catch { return ''; } });
  const [execution, setExecution] = useState(null);
  const [attachment, setAttachment] = useState(null);
  const request = useRef(null);
  const reset = () => { request.current?.abort(); setProposal(null); setReviewed(false); setMessage(''); setBusy(false); setExecution(null); };
  const contextKey = JSON.stringify([agentIds || null, context]);
  useEffect(() => { reset(); setAttachment(null); if (context || agentIds) setSavedId(''); }, [contextKey]);
  useEffect(() => {
    const events = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired'];
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
        if (!Array.isArray(response.data.agents) || response.data.agents.some(item => !item || typeof item.id !== 'string' || ['name', 'description', 'registration_status', 'system_prompt'].some(key => item[key] !== undefined && typeof item[key] !== 'string'))) throw new Error('Invalid agent catalog.');
        const available = agentIds ? response.data.agents.filter(item => agentIds.includes(item.id)) : response.data.agents;
        if (!controller.signal.aborted) { setAgents(available); setAgent(available[0]?.id || ''); }
      } else if (action === 'suggest') {
        setProposal(null); setReviewed(false);
        let file = null;
        if (attachment) {
          if (!attachment.size || attachment.size > 25 * 1024 * 1024) throw new Error('Select a nonempty attachment of at most 25 MB.');
          const encoded = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]); reader.onerror = () => reject(new Error('Could not read attachment.')); reader.readAsDataURL(attachment); });
          if (controller.signal.aborted) return;
          file = { filename: attachment.name, content_type: attachment.type || 'application/octet-stream', content_base64: encoded };
        }
        response = await agenticClient.post(url(`agents/${encodeURIComponent(agent)}/suggest`), { task: task.trim(), context: context || null, ...(file ? { attachment: file } : {}) }, options);
        if (!validProposal(response.data) || response.data.command.agent_id !== agent) throw new Error('Invalid agent proposal.');
        if (!controller.signal.aborted) {
          setProposal(response.data); setSavedId(response.data.recommendation_id || '');
          try { if (response.data.recommendation_id) sessionStorage.setItem('depo:agent-recommendation', response.data.recommendation_id); } catch { /* optional bookmark */ }
        }
      } else if (action === 'reload') {
        response = await agenticClient.get(url(`agent-recommendations/${encodeURIComponent(savedId.trim())}`), options);
        const value = response.data;
        if (contextIdentity(value.context || null) !== contextIdentity(context || null)) throw new Error('Saved recommendation belongs to a different page or selection. Request a new recommendation.');
        if (!validProposal(value) || (agentIds && !agentIds.includes(value.command.agent_id))) throw new Error('Invalid saved recommendation for this page.');
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
        response = await agenticClient.post(url('runs'), { ...command, approved_by: actor.trim(), approval_token: token, wait_for_completion: true }, options);
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
    <div className="depo-panel__header"><h3><Bot size={20} aria-hidden="true" /> {title}</h3><span className="depo-badge">Review before execution</span></div>
    <div className="depo-panel__body">
    <ol className="depo-action-steps" aria-label="Recommendation steps">
      <li><ListChecks size={18} aria-hidden="true" /><span><strong>1. Select</strong><small>Choose an agent for your task</small></span></li>
      <li><MessageSquare size={18} aria-hidden="true" /><span><strong>2. Describe</strong><small>Request a permitted action</small></span></li>
      <li><ShieldCheck size={18} aria-hidden="true" /><span><strong>3. Review</strong><small>Check inputs and approve execution</small></span></li>
    </ol>
    <p className="depo-agent-intro">Recommendations propose actions. Execution requires your review and any applicable approval.</p>
    <details><summary>Who recommends and who approves?</summary><p>The agent proposes a permitted action. The approver is the person authorised to review and accept its inputs. A recommendation does not grant approval.</p></details>
    <div className="depo-agent-compose">
    <div className="depo-agent-selection">
    <button disabled={busy} onClick={() => { reset(); operate('load'); }}>Load agents</button>
    <label>Agent <select aria-label="Recommendation agent" disabled={busy || !agents.length} value={agent} onChange={event => { reset(); setAgent(event.target.value); }}>{!agents.length && <option value="">Load agents to select an agent</option>}{agents.map(item => <option key={item.id} value={item.id}>{item.name || item.id}</option>)}</select></label>
    {agent && <p>{agents.find(item => item.id === agent)?.description} {agents.find(item => item.id === agent)?.registration_status}</p>}
    {agents.find(item => item.id === agent)?.system_prompt && <details><summary>Agent instructions from the catalog</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{agents.find(item => item.id === agent).system_prompt}</pre></details>}
    </div>
    <div className="depo-agent-task">
    <label>Task <textarea aria-label="Recommendation task" placeholder="Describe the outcome you need and the ontology or data to use…" rows={4} maxLength={8000} disabled={busy} value={task} onChange={event => { reset(); setTask(event.target.value); }} /></label>
    <label>Source attachment (for import tasks)<input type="file" disabled={busy} onChange={event => { reset(); setAttachment(event.target.files?.[0] || null); }} /></label>
    <button disabled={busy || !agent || !task.trim()} onClick={() => operate('suggest')}>Get recommendation</button>
    </div>
    </div>
    <details className="depo-saved-recommendation" open={!!savedId}><summary>Open a saved recommendation</summary>
    <label>Saved recommendation ID <input aria-label="Saved recommendation ID" value={savedId} disabled={busy} onChange={event => { reset(); setSavedId(event.target.value); }} /></label>
    <button disabled={busy || !savedId.trim()} onClick={() => { setProposal(null); setReviewed(false); operate('reload'); }}>Load saved recommendation</button>
    </details>
    {proposal && <div><strong>Proposed tool: {proposal.command.tool_id}</strong><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify({ ...proposal.command.inputs, ...(proposal.command.inputs?.file ? { file: { filename: proposal.command.inputs.file.filename, content_type: proposal.command.inputs.file.content_type, content: 'User-supplied attachment; binary content hidden' } } : {}) }, null, 2)}</pre>
      <details><summary>Prompt details</summary>{proposal.prompt_details ? <><p>Model: {proposal.prompt_details.model} · Prompt version: {proposal.prompt_details.prompt_version}</p><h4>User request</h4><pre style={{ whiteSpace: 'pre-wrap' }}>{proposal.prompt_details.user_request}</pre><h4>System instructions</h4><pre style={{ whiteSpace: 'pre-wrap' }}>{proposal.prompt_details.system_prompt}</pre><details><summary>Full model user prompt and tool context</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{proposal.prompt_details.user_prompt}</pre></details></> : <p>This older recommendation has no retained prompt snapshot.</p>}</details>
      <label>Approver <input aria-label="Recommendation steward" value={actor} disabled={busy} onChange={event => { setActor(event.target.value); setReviewed(false); }} /></label>
      <label><input type="checkbox" checked={reviewed} disabled={busy} onChange={event => setReviewed(event.target.checked)} />I reviewed the proposed action and inputs</label>
      <button disabled={busy || !reviewed || (proposal.requires_approval && !actor.trim())} onClick={() => operate('execute')}>Execute reviewed recommendation</button>
    </div>}
    {busy && <><button onClick={reset}>Stop waiting</button><p>Stopping the wait does not undo an execution. Inspect agent telemetry before retrying a write.</p></>}
    {message && <p role="status">{message}</p>}
    {execution && <><button onClick={() => window.dispatchEvent(new CustomEvent('depo:inspect-agent-run', {detail:execution}))}>{execution.execution_kind === 'workflow' ? 'Inspect workflow execution' : 'Inspect standalone execution'}</button><details open><summary>Execution result</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(execution.result, null, 2)}</pre></details></>}
    </div>
  </section>;
}
