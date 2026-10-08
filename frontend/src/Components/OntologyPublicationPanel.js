import React, { useEffect, useRef, useState } from 'react';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { getCredentialProfile } from '../services/serviceAuth';

export default function OntologyPublicationPanel({ ontologyId }) {
  const [metadata, setMetadata] = useState(null), [publication, setPublication] = useState(null);
  const [actor, setActor] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [missing, setMissing] = useState(false);
  const actionRequest = useRef(null);
  useEffect(() => {
    const invalidate = () => { actionRequest.current?.abort(); setActor(''); setMetadata(null); setPublication(null); setRevision(value => value + 1); };
    const events = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired'];
    events.forEach(event => window.addEventListener(event, invalidate));
    return () => { actionRequest.current?.abort(); events.forEach(event => window.removeEventListener(event, invalidate)); };
  }, [ontologyId]);
  const root = path => buildSemanticServiceUrl('ontology', `/api/v1/ontologies${path}`);
  useEffect(() => {
    const controller = new AbortController(); setMetadata(null); setPublication(null); setError(''); setBusy(false); setMissing(false);
    if (!ontologyId) return;
    Promise.all([apiClient.get(root(`/${encodeURIComponent(ontologyId)}`), { signal: controller.signal }).catch(failure => { failure.catalogMissing = failure.response?.status === 404; throw failure; }), apiClient.get(root(`/${encodeURIComponent(ontologyId)}/publication`), { signal: controller.signal })])
      .then(([record, receipt]) => { if (!controller.signal.aborted) {
        if (!record.data || !['draft', 'in_review', 'approved', 'deprecated', 'retired'].includes(record.data.lifecycle_status) ||
            !receipt.data || !['not_verified', 'not_published', 'unverified', 'publishing', 'published'].includes(receipt.data.status) ||
            (receipt.data.receipt && (!Number.isSafeInteger(receipt.data.receipt.resources) || receipt.data.receipt.resources < 0 || !Number.isSafeInteger(receipt.data.receipt.relationships) || receipt.data.receipt.relationships < 0))) throw new Error('Invalid publication response');
        setMetadata(record.data); setPublication(receipt.data);
      } })
      .catch(failure => { if (!controller.signal.aborted) { setMissing(!!failure.catalogMissing); setError(failure.catalogMissing ? 'Retained source needs catalog preparation before review.' : 'Could not verify ontology publication. Refresh before retrying.'); } });
    return () => controller.abort();
  }, [ontologyId, revision]);
  const act = async action => {
    if (busy) return; setBusy(true); setError('');
    const controller = new AbortController(); actionRequest.current = controller;
    const selected = ontologyId;
    try {
      const approval = { approved_by: actor.trim(), approval_token: getCredentialProfile('ONTOLOGY_APPROVAL_TOKEN') };
      const options = { signal: controller.signal };
      if (action === 'prepare') await apiClient.post(root('/migrations/legacy'), { ontology_ids: [selected] }, options);
      else if (action === 'publish') await apiClient.post(root(`/${encodeURIComponent(selected)}/publish`), approval, options);
      else await apiClient.post(root(`/${encodeURIComponent(selected)}/transition`), { ...approval, target: action, reason: 'Reviewed from Ontology Junction' }, options);
      if (!controller.signal.aborted) setRevision(value => value + 1);
    } catch (failure) { if (!controller.signal.aborted) setError(typeof failure.response?.data?.detail === 'string' ? failure.response.data.detail : 'Outcome unverified. Refresh publication status before retrying.'); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  if (!ontologyId) return null;
  return <section className="depo-panel" aria-label="Ontology publication">
    <div className="depo-panel__header"><h3>Neo4j publication</h3><span className="depo-badge">{publication?.status === 'published' ? 'Published' : metadata?.lifecycle_status || 'Not verified'}</span></div>
    <div className="depo-panel__body"><p>Registration retains the source. Review and approval allow a separate publication to Neo4j. The approver is the person authorised to accept this ontology; the agent cannot approve for you.</p>
      <label className="depo-field">Approver<input className="depo-input" value={actor} onChange={event => setActor(event.target.value)} placeholder="Your approval identity" /></label>
      {error && <p role="alert">{error}</p>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
        {missing && <button disabled={busy} onClick={() => act('prepare')}>Prepare retained source for review</button>}
        {metadata?.lifecycle_status === 'draft' && <button disabled={busy || !actor.trim()} onClick={() => act('in_review')}>Submit for review</button>}
        {metadata?.lifecycle_status === 'in_review' && <button disabled={busy || !actor.trim()} onClick={() => act('approved')}>Approve ontology</button>}
        {metadata?.lifecycle_status === 'approved' && publication?.status !== 'published' && <button disabled={busy || !actor.trim()} onClick={() => act('publish')}>Publish to Neo4j</button>}
        <button disabled={busy} onClick={() => setRevision(value => value + 1)}>Verify publication</button>
      </div>
      {publication && <p role="status">Graph status: {publication.status}. {publication.receipt ? `${publication.receipt.resources} resources; ${publication.receipt.relationships} relationships.` : 'No verified graph receipt is available.'}</p>}
    </div>
  </section>;
}
