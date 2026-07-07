import React, { useState } from 'react';

export default function AgentPanel({ onPropose, proposals = [], onApprove }) {
  const [prompt, setPrompt] = useState('');
  return <aside className="agent-panel"><h3>Agent Proposals</h3><textarea value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Ask for a diagram, validation explanation, impact analysis, or cleanup proposal." /><button type="button" onClick={() => onPropose?.(prompt)}>Propose</button><ul>{proposals.map((proposal) => <li key={proposal.id}><strong>{proposal.intent}</strong><span>{proposal.status}</span><button type="button" onClick={() => onApprove?.(proposal.id)}>Approve</button></li>)}</ul></aside>;
}
