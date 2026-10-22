// One result contract for the existing Governor and Steward tools.
export function agentToolResult(response, agent, tool) {
  const run = response?.data;
  if (!run?.result || typeof run.result !== 'object' || Array.isArray(run.result) ||
      typeof run.run_id !== 'string' || !run.run_id || (run.status && run.status !== 'completed') ||
      run.agent_id !== agent || run.tool_id !== tool) {
    throw new Error('Agent returned an incompatible result. Inspect agent telemetry before retrying.');
  }
  return { result: run.result, runId: run.run_id };
}

export function validBridgePolicy(result, previewId) {
  if (result?.preview_id !== previewId || result.policy !== 'validated-only-v1' ||
      !['ready','held'].includes(result.status) || !Array.isArray(result.decisions) || !Array.isArray(result.accepted_ids)) return false;
  const ids = result.decisions.map(row => row?.candidate_id);
  if (ids.some(id => typeof id !== 'string' || !id) || new Set(ids).size !== ids.length ||
      result.decisions.some(row => !['publish','hold'].includes(row.decision) || !Array.isArray(row.reasons) || row.reasons.some(reason => typeof reason !== 'string') || (row.decision === 'publish' && row.reasons.length))) return false;
  const accepted = result.decisions.filter(row => row.decision === 'publish').map(row => row.candidate_id).sort();
  return JSON.stringify(accepted) === JSON.stringify([...result.accepted_ids].sort()) &&
    result.held_count === ids.length - accepted.length && result.status === (accepted.length ? 'ready' : 'held');
}
