import React, {useEffect, useRef, useState} from 'react';
import {apiClient} from '../../services/apiClient';
import {buildUrl} from '../../config';
import {apiErrorMessage} from '../../utils/apiErrorMessage';

export default function OntologyFoundationPanel({ontologyId}) {
  const [foundation,setFoundation] = useState(null);
  const [result,setResult] = useState(null);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const request = useRef(null);
  const selected = useRef(ontologyId);
  selected.current = ontologyId;
  useEffect(() => {
    const controller = new AbortController();
    apiClient.get(buildUrl('/api/v1/ontologies/foundation'),{signal:controller.signal}).then(response => {
      if(!controller.signal.aborted) setFoundation(response.data);
    }).catch(failure => {if(!controller.signal.aborted) setError(apiErrorMessage(failure));});
    return () => controller.abort();
  },[]);
  useEffect(() => {
    request.current?.abort(); setResult(null); setError(''); setBusy(false);
    return () => request.current?.abort();
  },[ontologyId]);
  async function check() {
    if(busy || !ontologyId) return;
    const id = ontologyId, controller = new AbortController();
    request.current = controller; setBusy(true); setError(''); setResult(null);
    try {
      const response = await apiClient.get(buildUrl(`/api/v1/ontologies/${encodeURIComponent(id)}/consistency`),{signal:controller.signal,timeout:190000});
      if(response.data?.ontology_id !== id) throw new Error('Consistency result does not match the selected ontology. Refresh and retry.');
      if(!controller.signal.aborted && selected.current===id) setResult(response.data);
    } catch(failure) {if(!controller.signal.aborted && selected.current===id) setError(apiErrorMessage(failure));}
    finally {if(request.current===controller && !controller.signal.aborted) setBusy(false);}
  }
  return <section aria-label="Embedded semantic foundation" style={{borderBottom:'1px solid var(--theme-color-soft-bdr)',padding:'0 0 16px',marginBottom:16}}>
    <h3>Embedded semantic foundation</h3>
    <p>IDO 4.2 and DEPO business core distinguish physical parts, designs, documents and activities. Source mappings still require review.</p>
    {!foundation && !error && <p role="status">Checking foundation availability…</p>}
    {foundation && <p>{foundation.owl_dl?.available ? 'OWL-DL engine available' : 'OWL-DL engine unavailable: install the verified worker and Java runtime.'} · Foundation bundled for offline use.</p>}
    <button type="button" disabled={busy || !ontologyId || !foundation?.owl_dl?.available} onClick={check}>{busy?'Checking logical consistency…':'Check OWL-DL consistency'}</button>
    <p>The check covers the retained ontology and embedded foundation. External graph instances and unapproved imports are outside this scope. No graph changes are published.</p>
    {error && <p role="alert">{error}</p>}
    {result && <div aria-label="OWL-DL result">
      <p role="status"><strong>{result.status==='consistent' && result.consistency_verified ? 'Consistent within checked scope' : result.status==='inconsistent' && result.consistency_verified ? 'Logical inconsistency detected' : 'Consistency not established'}</strong></p>
      {result.reason && <p>Reason: {String(result.reason).replaceAll('_',' ')}.</p>}
      {result.unsatisfiable_class_count > 0 && <p role="alert">{result.unsatisfiable_class_count} unsatisfiable classes need review. Overall consistency alone does not establish a coherent model.</p>}
      {result.alignment && <p>{result.alignment.classes_with_foundation_path} of {result.alignment.domain_classes} declared domain classes have explicit subclass paths to the foundation. This does not approve their meaning or establish ISO conformance.</p>}
      {result.unsatisfiable_classes?.length > 0 && <details><summary>Classes needing review</summary><ul>{result.unsatisfiable_classes.map(iri=><li key={iri}>{iri}</li>)}</ul></details>}
      <details><summary>Validation scope and evidence</summary><dl>
        <dt>Artifact digest</dt><dd style={{overflowWrap:'anywhere'}}>{result.artifact_sha256}</dd>
        <dt>Foundation version</dt><dd>{result.foundation?.version_iri}</dd>
        <dt>Reasoner</dt><dd>{result.engine || 'Not executed'} {result.engine_version || ''}</dd>
        <dt>Checked</dt><dd>{result.checked_at}</dd>
      </dl></details>
    </div>}
    <p>Logical consistency does not prove real-world correctness, complete data or approved alignment.</p>
  </section>;
}
