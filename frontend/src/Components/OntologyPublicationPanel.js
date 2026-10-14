import React, { useEffect, useRef, useState } from 'react';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { getCredentialProfile } from '../services/serviceAuth';

export default function OntologyPublicationPanel({ ontologyId, onPublished, fromWorkflow = false }) {
  const [metadata, setMetadata] = useState(null), [publication, setPublication] = useState(null);
  const [actor, setActor] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  const [missing, setMissing] = useState(false);
  const actionRequest = useRef(null);
  const [activeAction, setActiveAction] = useState('');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  useEffect(() => {
    setElapsedSeconds(0);
    if (!busy || activeAction !== 'publish') return;
    const started = Date.now();
    const timer = setInterval(() => setElapsedSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [busy, activeAction]);
  const notifiedReceipt = useRef('');
  const onPublishedRef = useRef(onPublished);
  onPublishedRef.current = onPublished;
  useEffect(() => {
    if (publication?.status !== 'published' || !publication.receipt) return;
    const identity = ontologyId + ':' + JSON.stringify(publication.receipt);
    if (notifiedReceipt.current === identity) return;
    notifiedReceipt.current = identity;
    onPublishedRef.current?.(publication.receipt);
    window.dispatchEvent(new CustomEvent('depo:ontologies-changed'));
  }, [ontologyId, publication]);
  useEffect(() => {
    const invalidate = () => { actionRequest.current?.abort(); setActiveAction(''); notifiedReceipt.current = ''; setActor(''); setMetadata(null); setPublication(null); setRevision(value => value + 1); };
    const events = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired'];
    events.forEach(event => window.addEventListener(event, invalidate));
    return () => { actionRequest.current?.abort(); events.forEach(event => window.removeEventListener(event, invalidate)); };
  }, [ontologyId]);
  const root = path => buildSemanticServiceUrl('ontology', `/api/v1/ontologies${path}`);
  useEffect(() => {
    const controller = new AbortController(); setMetadata(null); setPublication(null); setError(''); setBusy(false); setActiveAction(''); setMissing(false);
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
  useEffect(() => {
    if (busy || publication?.status !== 'publishing') return;
    const timer = setTimeout(() => setRevision(value => value + 1), 5000);
    return () => clearTimeout(timer);
  }, [busy, publication]);
  const act = async action => {
    if (busy) return; setBusy(true); setActiveAction(action); setError('');
    const controller = new AbortController(); actionRequest.current = controller;
    const selected = ontologyId;
    try {
      const approval = { approved_by: actor.trim(), approval_token: getCredentialProfile('ONTOLOGY_APPROVAL_TOKEN') };
      const options = { signal: controller.signal, timeout: 30000 };
      if (action === 'prepare') await apiClient.post(root('/migrations/legacy'), { ontology_ids: [selected] }, options);
      else if (action === 'publish') {
        const response = await apiClient.post(root(`/${encodeURIComponent(selected)}/publish?background=true`), approval, { ...options, timeout: 30000 });
        if (!controller.signal.aborted && response.data?.job_id) setPublication({ status: 'publishing', phase: 'queued', job_id: response.data.job_id });
      }
      else if (action === 'cancel') await apiClient.post(root(`/${encodeURIComponent(selected)}/publication-jobs/${encodeURIComponent(publication.job_id)}/cancel`), approval, options);
      else await apiClient.post(root(`/${encodeURIComponent(selected)}/transition`), { ...approval, target: action, reason: fromWorkflow ? 'Reviewed from import workflow' : 'Reviewed from Ontology Junction' }, options);
      if (!controller.signal.aborted) { setRevision(value => value + 1); window.dispatchEvent(new CustomEvent('depo:ontologies-changed')); }
    } catch (failure) { if (!controller.signal.aborted) {
      if (action === 'publish') setPublication({ status: 'unverified' });
      setError(typeof failure.response?.data?.detail === 'string' ? failure.response.data.detail : 'Outcome unverified. Refresh publication status before retrying.');
    } }
    finally { if (!controller.signal.aborted) { setBusy(false); setActiveAction(''); } }
  };
  if (!ontologyId) return null;
  return <section className="depo-panel" aria-label="Ontology publication">
    <div className="depo-panel__header"><h3>Neo4j publication</h3><span className="depo-badge">{(busy && activeAction === 'publish') || publication?.status === 'publishing' ? 'Publishing...' : publication?.status === 'published' ? 'Published' : publication?.status === 'unverified' ? 'Verification needed' : metadata?.lifecycle_status || 'Not verified'}</span></div>
    <div className="depo-panel__body"><p>Registration retains the source. Review and approval allow a separate publication to Neo4j. The approver is the person authorised to accept this ontology; the agent cannot approve for you.</p>
      {fromWorkflow && <p><a href={`#/ontology?target=${encodeURIComponent(ontologyId)}`} target="_blank" rel="noopener noreferrer">View in Ontology Junction</a> (opens in a new tab). Review the ontology there, then return here to approve and publish.</p>}
      <label className="depo-field">Approver<input className="depo-input" value={actor} onChange={event => setActor(event.target.value)} placeholder="Your approval identity" /></label>
      {busy && <p role="status" aria-live="polite">{activeAction === 'publish' ? 'Submitting background publication. Once queued, processing continues after you leave this page.' : 'Updating ontology lifecycle...'}</p>}
      {busy && activeAction === 'publish' && <p>Elapsed: {elapsedSeconds}s.{elapsedSeconds >= 60 && ' Large ontologies require RDF preparation and a graph transaction. If this continues, inspect ontology.err.log and graph.err.log for the current publication phase.'}</p>}
      {publication?.status === 'unverified' && <p role="alert">Publication outcome is uncertain. Restore service connectivity and choose Verify publication. Publish remains disabled until a current receipt or an idle publisher is verified.</p>}
      {!busy && publication?.status === 'publishing' && <p role="status">Publication {publication.phase === 'queued' ? 'queued' : 'running'} in the background. You can leave this page; status refreshes automatically when you return. {publication.job_id && `Job: ${publication.job_id}`}</p>}
      {error && <p role="alert">{error}</p>}
      {Number.isSafeInteger(publication?.progress?.resource_offset) && Number.isSafeInteger(publication?.progress?.resources_expected) && <p role="status">Staged resources: {publication.progress.resource_offset} / {publication.progress.resources_expected}. Staged data becomes visible only after validation and activation.</p>}
      {publication?.resumable && <p>Incomplete batches are retained. Publish again to resume the same approved artifact from its checkpoint.</p>}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 12 }}>
        {missing && <button disabled={busy} onClick={() => act('prepare')}>Prepare retained source for review</button>}
        {metadata?.lifecycle_status === 'draft' && <button disabled={busy || !actor.trim()} onClick={() => act('in_review')}>Submit for review</button>}
        {metadata?.lifecycle_status === 'in_review' && <button disabled={busy || !actor.trim()} onClick={() => act('approved')}>Approve ontology</button>}
        {metadata?.lifecycle_status === 'approved' && publication?.status !== 'published' && <button disabled={busy || !actor.trim() || !['not_published', 'not_verified'].includes(publication?.status)} onClick={() => act('publish')}>Publish to Neo4j</button>}
        {publication?.phase === 'queued' && publication?.job_id && <button disabled={busy || !actor.trim()} onClick={() => act('cancel')}>Cancel queued publication</button>}
        <button disabled={busy} onClick={() => setRevision(value => value + 1)}>Verify publication</button>
      </div>
      {publication && <p role="status">Graph status: {busy && activeAction === 'publish' ? 'publishing (request in progress)' : publication.status}. {publication.receipt ? `${publication.receipt.resources} resources; ${publication.receipt.relationships} relationships.` : 'No verified graph receipt is available.'}</p>}
    </div>
  </section>;
}
