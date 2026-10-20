import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { apiErrorMessage } from '../utils/apiErrorMessage';

export default function IngestedDataInventory({ ontologies = [] }) {
  const [state, setState] = useState({ loading: true, tasks: [], error: '' });
  const [refresh, setRefresh] = useState(0);
  const [search, setSearch] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: true, tasks: [], error: '' });
    apiClient.get(buildSemanticServiceUrl('ingestion', '/api/v1/import/tasks'),
      { signal: controller.signal, timeout: 15000 }).then(response => {
      if (!Array.isArray(response.data?.tasks)) throw new Error('Import registry returned an invalid task collection.');
      if (!controller.signal.aborted) setState({ loading: false, tasks: response.data.tasks, error: '' });
    }).catch(error => {
      if (!controller.signal.aborted) setState({ loading: false, tasks: [], error: apiErrorMessage(error, 'Ingested-data inventory is unavailable.') });
    });
    const invalidate = () => setRefresh(value => value + 1);
    window.addEventListener('depo:credentials-changed', invalidate);
    window.addEventListener('depo:credentials-cleared', invalidate);
    return () => { controller.abort(); window.removeEventListener('depo:credentials-changed', invalidate); window.removeEventListener('depo:credentials-cleared', invalidate); };
  }, [refresh]);
  const tasks = state.tasks.filter(task => `${task.filename || ''} ${task.task_id || ''} ${task.status || ''}`.toLowerCase().includes(search.toLowerCase()));
  return <section aria-label="Ingested data inventory">
    <h3>Ingested data inventory</h3>
    <p>Retained import records and registered ontology versions are discoverable before product publication. An import record alone does not certify graph completeness, quality or product approval.</p>
    <button onClick={() => setRefresh(value => value + 1)} disabled={state.loading}>Refresh ingested data</button>
    <label>Find ingested source <input value={search} onChange={event => setSearch(event.target.value)} /></label>
    {state.loading && <p role="status">Loading retained imports…</p>}
    {state.error && <p role="alert">{state.error}</p>}
    {!state.loading && !state.error && <>
      <p>{state.tasks.length} retained import records; {tasks.length} match the filter. <a href="#/import">Review imports and graph loading</a></p>
      {!state.tasks.length && <p>No retained import records were returned by the ingestion service.</p>}
      <div style={{ overflow: 'auto', maxHeight: 400 }}><table><thead><tr><th>Source</th><th>Task ID</th><th>Format</th><th>Import status</th><th>Stage</th><th>Started</th></tr></thead><tbody>
        {tasks.map(task => <tr key={task.task_id}><td>{task.filename || 'Unnamed source'}</td><td>{task.task_id}</td><td>{task.file_type || 'Unknown'}</td><td>{task.status || 'Unknown'}</td><td>{task.current_stage || 'Unknown'}</td><td>{task.started_at || 'Unavailable'}</td></tr>)}
      </tbody></table></div>
    </>}
    <h4>Registered ontology versions ({ontologies.length})</h4>
    <ul>{ontologies.map(ontology => <li key={ontology.ontology_id}><a href={`#/ontology?target=${encodeURIComponent(ontology.ontology_id)}`}>{ontology.label || ontology.ontology_id}</a> — {ontology.ontology_id}</li>)}</ul>
  </section>;
}
