import React, { useEffect, useRef, useState } from 'react';
import { apiClient } from '../../services/apiClient';
import { buildSemanticServiceUrl } from '../../config';
import { getCredentialProfile } from '../../services/serviceAuth';
import { apiErrorMessage } from '../../utils/apiErrorMessage';

export default function OntologyReleasePanel({ ontologyId, actor = '' }) {
  const [data, setData] = useState(null), [error, setError] = useState('');
  const [busy, setBusy] = useState(false), [refresh, setRefresh] = useState(0);
  const [form, setForm] = useState({ family_id: '', version: '', predecessor_id: '', change_kind: 'initial', change_notes: '' });
  const request = useRef(null), pending = useRef(false);
  const url = buildSemanticServiceUrl('ontology', `/api/v1/ontologies/${encodeURIComponent(ontologyId)}/releases`);
  useEffect(() => {
    const invalidate = () => {
      request.current?.abort(); pending.current = false; setData(null); setBusy(false); setError('');
      setRefresh(value => value + 1);
    };
    const events = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired'];
    events.forEach(name => window.addEventListener(name, invalidate));
    return () => { request.current?.abort(); events.forEach(name => window.removeEventListener(name, invalidate)); };
  }, [ontologyId]);
  useEffect(() => {
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    pending.current = true; setBusy(true); setError(''); setData(null);
    apiClient.get(url, { signal: controller.signal, timeout: 30000 }).then(response => {
      if (controller.signal.aborted) return;
      if (response.data?.ontology_id !== ontologyId || !Array.isArray(response.data.history)) throw new Error('Release response does not match the selected ontology');
      setData(response.data);
    }).catch(failure => { if (!controller.signal.aborted) setError(apiErrorMessage(failure)); })
      .finally(() => { if (!controller.signal.aborted) { pending.current = false; setBusy(false); } });
    return () => controller.abort();
  }, [url, ontologyId, refresh]);
  const declare = async event => {
    event.preventDefault();
    if (pending.current || !data || data.release || !actor.trim()) return;
    const controller = new AbortController(); request.current = controller;
    pending.current = true; setBusy(true); setError('');
    try {
      const response = await apiClient.post(url, { ...form, predecessor_id: form.predecessor_id || null,
        approved_by: actor.trim(), approval_token: getCredentialProfile('ONTOLOGY_APPROVAL_TOKEN') },
        { signal: controller.signal, timeout: 30000 });
      if (controller.signal.aborted) return;
      if (response.data?.ontology_id !== ontologyId || response.data.version !== form.version) throw new Error('Release receipt does not match this declaration');
      setRefresh(value => value + 1);
    } catch (failure) {
      if (!controller.signal.aborted) setError(`Declaration outcome needs verification. Refresh release history before retrying. ${apiErrorMessage(failure)}`);
    } finally {
      if (!controller.signal.aborted) { pending.current = false; setBusy(false); }
    }
  };
  const field = (name, label) => <label className="depo-field">{label}<input className="depo-input" value={form[name]} disabled={busy} maxLength={name === 'version' ? 32 : 64} required={name !== 'predecessor_id'} onChange={e => setForm({ ...form, [name]: e.target.value })} /></label>;
  return <div aria-label="Ontology release versions">
    <p>A release identifies one retained artifact. It does not approve, publish or migrate mappings. Change classification is a reviewer declaration, not verified compatibility.</p>
    <button type="button" disabled={busy} onClick={() => setRefresh(value => value + 1)}>Refresh release history</button>
    {busy && <p role="status">Checking release records…</p>}
    {error && <p role="alert">{error}</p>}
    {data?.release && <>
      <p>{data.release.family_id} · {data.release.version} · {data.release.change_kind}</p>
      {data.artifact_matches_release !== true && <p role="alert">The retained artifact does not match its release. Restore the exact source or register a new version before publication.</p>}
      <div style={{ overflowX: 'auto' }}><table><caption>Declared release history</caption><thead><tr><th>Version</th><th>Ontology</th><th>Change</th><th>Notes</th></tr></thead><tbody>{data.history.map(row => <tr key={row.ontology_id}><td>{row.version}</td><td><a href={`#/ontology?target=${encodeURIComponent(row.ontology_id)}`}>{row.ontology_id}</a></td><td>{row.change_kind}</td><td>{row.change_notes}</td></tr>)}</tbody></table></div>
    </>}
    {data && !data.release && <form onSubmit={declare}>
      <p>No release version is declared for this artifact. Existing lifecycle controls remain available. Enter the approver above to declare a version.</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 12 }}>
        {field('family_id', 'Ontology family (for example AP242)')}
        {field('version', 'Version (for example 1.0.0)')}
        {field('predecessor_id', 'Previous ontology ID (blank for first release)')}
        <label className="depo-field">Change classification<select className="depo-input" disabled={busy} value={form.change_kind} onChange={e => setForm({ ...form, change_kind: e.target.value })}><option value="initial">First release</option><option value="breaking">Breaking — major increment</option><option value="additive">Additive — minor increment</option><option value="corrective">Corrective — patch increment</option></select></label>
      </div>
      <label className="depo-field">Change notes<textarea className="depo-input" required disabled={busy} maxLength={8000} value={form.change_notes} onChange={e => setForm({ ...form, change_notes: e.target.value })} /></label>
      <button type="submit" disabled={busy || !actor.trim() || !form.family_id || !form.version || !form.change_notes.trim()}>Declare immutable release</button>
    </form>}
  </div>;
}
