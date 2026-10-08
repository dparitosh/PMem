import React, { useEffect, useRef, useState } from 'react';
import { useOntologies } from '../../contexts/OntologyContext';
import agenticAPI from '../../services/agenticApi';
import { apiClient } from '../../services/apiClient';
import { buildSemanticServiceUrl } from '../../config';
import { apiErrorMessage } from '../../utils/apiErrorMessage';

const contexts = [
  ['Part and revision', 'Inspected product', 'Design revision and inspected serial identity'],
  ['Geometry / design feature', 'Inspection feature', 'Geometry references and coordinate system'],
  ['Dimension / geometric tolerance', 'Characteristic definition and nominal', 'PMI meaning, tolerance values and units'],
  ['Datum / datum reference frame', 'Inspection datum context', 'Datum precedence and reference frame'],
  ['Design requirement', 'Measurement result via characteristic', 'Characteristic identity, execution and provenance'],
];
export default function QifAp242Mapping() {
  const { ontologies, loading, error: registryError, fetchOntologies } = useOntologies();
  const [qif, setQif] = useState(''); const [ap242, setAp242] = useState('');
  const [agentReport, setAgentReport] = useState(null);
  const [evidence, setEvidence] = useState(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false);
  const request = useRef(null);
  useEffect(() => { request.current?.abort(); setEvidence(null); setAgentReport(null); setError(''); setBusy(false); }, [qif, ap242]);
  useEffect(() => {
    const clear = () => { request.current?.abort(); setEvidence(null); setAgentReport(null); setError(''); setBusy(false); };
    const events = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-expired'];
    events.forEach(event => window.addEventListener(event, clear));
    return () => { request.current?.abort(); events.forEach(event => window.removeEventListener(event, clear)); };
  }, []);
  const selectedAvailable = id => ontologies.some(item => item.value === id && !item.disabled);
  useEffect(() => {
    if (loading) return;
    if ((qif && !selectedAvailable(qif)) || (ap242 && !selectedAvailable(ap242))) {
      request.current?.abort(); setEvidence(null); setAgentReport(null); setBusy(false);
      setError('A selected ontology is no longer available. Select its current registered version.');
    }
  }, [ontologies, loading, qif, ap242]);
  const inspect = async () => {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(''); setEvidence(null);
    try {
      const results = await Promise.all([qif, ap242].map(id => apiClient.get(buildSemanticServiceUrl('ingestion', `/api/v1/ontology/${encodeURIComponent(id)}/retained-inventory`), { signal: controller.signal, timeout: 30000 })));
      if (controller.signal.aborted) return;
      const inventories = results.map((response, index) => {
        const data = response.data;
        if (data?.ontology_id !== [qif, ap242][index] || data.scope !== 'retained-ontology-version' || !Array.isArray(data.nodes)) {
          throw new Error('The service did not return a version-specific ontology inventory.');
        }
        if (!data.nodes.length) throw new Error('The selected retained ontology contains no inspectable terms.');
        return {
          entities: data.nodes.filter(node => node.kind === 'Class'),
          properties: data.nodes.filter(node => node.kind === 'DatatypeProperty'),
          relationships: data.nodes.filter(node => node.kind === 'ObjectProperty'),
        };
      });
      setEvidence({ qif_ontology_id: qif, ap242_ontology_id: ap242, inventories, status: 'review_required', scope: 'Structural inventories only; no engineering equivalence or instance links have been established.' });
    } catch (failure) { if (!controller.signal.aborted) setError(apiErrorMessage(failure)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const review = async () => {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setBusy(true); setError(''); setAgentReport(null);
    try {
      const response = await agenticAPI.orchestrateOntology({ workflow_id: 'qif_ap242_review', qif_ontology_id: qif, ap242_ontology_id: ap242 }, { signal: controller.signal, timeout: 120000 });
      if (controller.signal.aborted) return;
      if (response.data?.qif_ontology_id !== qif || response.data?.ap242_ontology_id !== ap242) throw new Error('Agent response belongs to another ontology selection.');
      setAgentReport(response.data);
    } catch (failure) { if (!controller.signal.aborted) setError(apiErrorMessage(failure)); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  };
  const choices = (value, change, label) => <label>{label}<select aria-label={label} value={value} onChange={event => change(event.target.value)} style={{ display: 'block', width: '100%', background: 'var(--ui-surface)', color: 'var(--ui-text)', padding: 8 }}>
    <option value="">Select registered ontology version</option>{ontologies.filter(item => { const text = `${item.label} ${item.prefix} ${item.namespace}`.toLowerCase(); return label.startsWith('QIF') ? text.includes('qif') : text.includes('ap242'); }).map(item => <option key={item.value} value={item.value} disabled={item.disabled}>{item.label} — {item.value}</option>)}
  </select></label>;
  return <section className="depo-panel" style={{ marginTop: 16, padding: 16 }} aria-busy={busy}>
    <h3>QIF ↔ AP242 mapping and traceability</h3>
    <p>Select the exact registered versions. The mapping direction here is QIF inspection evidence to AP242 design context. Selection uses registry names/prefixes/namespaces to identify likely standards; verify the retained schema version. This inspector does not propose mapping candidates or convert files.</p>
    {registryError && <p role="alert">{String(registryError)}</p>}
    <button type="button" className="depo-button" disabled={loading} onClick={() => fetchOntologies(true)}>Refresh ontology registry</button>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>{choices(qif, setQif, 'QIF ontology')}{choices(ap242, setAp242, 'AP242 ontology')}</div>
    <button type="button" className="depo-button" disabled={busy || !selectedAvailable(qif) || !selectedAvailable(ap242) || qif === ap242} onClick={inspect}>{busy ? 'Inspecting…' : 'Inspect selected schema inventories'}</button>
    <button type="button" className="depo-button" disabled={busy || !selectedAvailable(qif) || !selectedAvailable(ap242) || qif === ap242 || !agenticAPI.isConfigured()} onClick={review}>Run QIF–AP242 agent review</button>
    {agentReport && <div role="status"><p>{agentReport.scope}</p><p>Review required: {(agentReport.checks_required || []).join('; ')}</p>
      {agentReport.steps?.map(step => <div key={step.agent}><strong>{step.agent}</strong>{Array.isArray(step.result?.issues) && <p>{step.result.issues.length} structural issues</p>}</div>)}
      <p>{agentReport.steps?.at(-1)?.result?.unmatched_count ?? 'Unknown'} unmatched; {agentReport.steps?.at(-1)?.result?.ambiguous_count ?? 'Unknown'} ambiguous</p>
      <ul>{(agentReport.steps?.at(-1)?.result?.alignment_candidates || []).map((candidate, index) => <li key={index}>{candidate.source} [{(candidate.source_iris || []).join(', ')}] → {candidate.target_iri}{candidate.source_identity_ambiguous ? ' — ambiguous source identity' : ''} ({candidate.evidence}); unresolved: {(candidate.unresolved_checks || []).join(', ')}</li>)}</ul>
      {(agentReport.source_truncated || agentReport.steps?.at(-1)?.result?.candidate_limit_reached) && <p>Inspection was bounded; review the full ontology before approval.</p>}
    </div>}
    {qif && qif === ap242 && <p role="alert">Select two different ontology versions.</p>}
    {error && <p role="alert">{error}</p>}
    {evidence && <div role="status"><p>{evidence.scope}</p>{evidence.inventories.map((item, index) => <p key={index}>{index ? 'AP242' : 'QIF'}: {item.entities.length} entities, {item.properties.length} properties, {item.relationships.length} relationships.</p>)}</div>}
    <div style={{ overflowX: 'auto' }}><table style={{ width: '100%' }}><caption>Conceptual mapping checklist — not schema-field equivalences</caption><thead><tr><th scope="col">AP242 context</th><th scope="col">QIF context</th><th scope="col">Required evidence</th></tr></thead><tbody>{contexts.map(row => <tr key={row[0]}>{row.map(cell => <td key={cell}>{cell}</td>)}</tr>)}</tbody></table></div>
    <p>For instance linking, import QIF instance evidence first, then open Semantic Bridge in Ontology Junction, select AP242 as target and the corresponding import run. Review identity, units, revision, domain/range and provenance before approval. A verified AP242–QIF mapping profile is still required.</p>
    <a className="depo-button" href={`#/ontology?target=${encodeURIComponent(ap242)}&qif=${encodeURIComponent(qif)}&view=alignment`}>Open Ontology Junction / Semantic Bridge</a>
  </section>;
}
