import { confirmedSubmissionRejection } from '../services/workflowSubmission';
import './XmlAnalyticsLoader.css';
import AnalyticsViewBuilder from './AnalyticsViewBuilder';
import React, { useEffect, useRef, useState } from 'react';
import { apiClient, dataPipelineAPI } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { getCredentialProfile } from '../services/serviceAuth';
import { apiErrorMessage, withApiRequestId } from '../utils/apiErrorMessage';
import { pipelineRunLink } from '../workflows/runTracking';

const RECOVERY_KEY = 'depo-xml-analytics-recovery';
function retainedSubmission() {
  try {
    const value = JSON.parse(sessionStorage.getItem(RECOVERY_KEY));
    if (value && (value.unknown === true || typeof value.run_id === 'string')) return value;
  } catch { /* Browser storage may be unavailable. */ }
  return null;
}
export default function XmlAnalyticsLoader({ runEvidence = null, sources = [], selectedSchemaId = '', expanded = false }) {
  const [sourceId,setSourceId]=useState(selectedSchemaId);

  const [jobs, setJobs] = useState([]);
  const [job, setJob] = useState('');
  const [fields, setFields] = useState({ schema_artifact_id: '', xml_artifact_id: '', schema_prefix: 'depo_analytics', approved_by: '' });
  const [dependencies, setDependencies] = useState('{}');
  const [business, setBusiness] = useState('[]');
  const [constraintPolicy, setConstraintPolicy] = useState('strict');
  const [businessBinding, setBusinessBinding] = useState('');
  const [recovery, setRecovery] = useState(retainedSubmission);
  const [manualRun, setManualRun] = useState('');
  const [absenceConfirmed, setAbsenceConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState(null);
  const [xmlFile, setXmlFile] = useState(null);
  const mounted = useRef(true);
  const locked = useRef(false);
  const generation = useRef(0);
  const sourceRequest=useRef(null);
  useEffect(()=>{
    generation.current++;sourceRequest.current?.abort();setSourceId(selectedSchemaId);
    if(!recovery){setFields(previous=>({...previous,schema_artifact_id:''}));setDependencies('{}');setBusiness('[]');setBusinessBinding('');}
  },[selectedSchemaId]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; sourceRequest.current?.abort(); }; }, []);
  useEffect(() => {
    const invalidate = () => {
      generation.current += 1;
      setJobs([]); setJob(''); setReceipt(null); setError('Access changed. Refresh the retained task before submitting another load.');
    };
    const events = ['depo:credentials-changed', 'depo:credentials-cleared', 'depo:session-replaced', 'depo:session-expired'];
    events.forEach(event => window.addEventListener(event, invalidate));
    return () => events.forEach(event => window.removeEventListener(event, invalidate));
  }, []);
  useEffect(() => {
    if (recovery || receipt) return;
    const artifacts = Array.isArray(runEvidence?.artifacts) ? runEvidence.artifacts : [];
    const schema = artifacts.find(value => value?.kind === 'schema')?.artifact_id;
    const instance = artifacts.find(value => value?.kind === 'instance')?.artifact_id;
    setFields(previous => ({ ...previous,
      schema_artifact_id: schema || '',
      xml_artifact_id: instance || '',
    }));
    setBusiness('[]'); setBusinessBinding('');
    setDependencies(JSON.stringify(Object.fromEntries(artifacts.filter(value => value?.kind === 'schema-dependency' && value.relative_path && value.artifact_id).map(value => [value.relative_path, value.artifact_id]))));
  }, [runEvidence]);
  function remember(value) {
    setRecovery(value); setAbsenceConfirmed(false);
    try { if (value) sessionStorage.setItem(RECOVERY_KEY, JSON.stringify(value)); else sessionStorage.removeItem(RECOVERY_KEY); } catch { /* Keep the current run visible if storage is unavailable. */ }
  }
  useEffect(()=>{if(expanded)perform(false);},[expanded]);
  async function perform(submit) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError('');
    const startedGeneration = generation.current;
    const current = () => mounted.current && startedGeneration === generation.current;
    let submitted = false;
    try {
      if (submit === 'schema') {
        const controller=new AbortController();sourceRequest.current=controller;
        const source=sources.find(value=>value.ontology_id===sourceId);
        if(!source)throw new Error('Select an imported schema.');
        const response=await apiClient.get(buildSemanticServiceUrl('ingestion','/api/v1/reports/xsd-relational'),{params:{ontology_id:sourceId},timeout:30000,signal:controller.signal});
        if(!response.data?.schema_artifact_id)throw new Error('The selected schema has no retained XSD source. Reimport its complete schema set.');
        if(current()){setFields(previous=>({...previous,schema_artifact_id:response.data.schema_artifact_id}));setBusiness('[]');setBusinessBinding('');setDependencies(JSON.stringify(Object.fromEntries((source.data_product_draft?.artifacts||[]).filter(value=>value.kind==='schema-dependency'&&value.relative_path&&value.artifact_id).map(value=>[value.relative_path,value.artifact_id]))));}
      } else if (submit === 'refresh') {
        const id = recovery?.run_id || manualRun.trim();
        if (!id) throw new Error('Enter the retained run ID from Data Flow history.');
        const response = await dataPipelineAPI.getRun(id);
        if (response.data?.run_id !== id) throw new Error('The status response does not match this run.');
        if (current()) { remember({ run_id: id }); setReceipt({ status: response.data.status, run_manifest: response.data }); }
      } else if (submit === 'reconcile') {
        const id = recovery?.run_id;
        const token = getCredentialProfile('DATA_JOB_EXECUTION_TOKEN');
        if (!id || !token || !fields.approved_by.trim()) throw new Error('Enter an execution identity and connect data-job execution access.');
        const response = await dataPipelineAPI.reconcileAnalytics(id, { approved_by: fields.approved_by.trim(), approval_token: token });
        if (response.data?.run_manifest?.run_id !== id) throw new Error('The evidence response does not match this run.');
        if (current()) setReceipt(response.data);
      } else if (submit === 'upload') {
        if (!xmlFile) throw new Error('Select an Data file (XML).');
        const token = getCredentialProfile('INGESTION_WRITE_TOKEN');
        if (!token) throw new Error('Connect ingestion write access in Admin.');
        const body = new FormData(); body.append('file', xmlFile);
        const response = await apiClient.post(buildSemanticServiceUrl('ingestion', '/api/v1/analytics/xml-artifacts'), body,
          { headers: { Authorization: `Bearer ${token}` }, timeout: 60000 });
        if (current()) { setFields(previous => ({ ...previous, xml_artifact_id: response.data.artifact.artifact_id })); if (!recovery) setReceipt(null); }
      } else if (!submit) {
        const response = await dataPipelineAPI.definitions();
        const values = response.data?.definitions;
        if (!Array.isArray(values)) throw new Error('Invalid job-definition response.');
        if (current()){const approved=values.filter(value => value.job_type === 'xml-analytics-materialize' && value.lifecycle_state === 'approved' && value.enabled);setJobs(approved);if(approved.length===1)setJob(`${approved[0].job_id}:${approved[0].version}`);}
      } else {
        if (recovery) throw new Error('Check the retained task before preparing another submission.');
        if (!recovery) setReceipt(null);
        const selected = jobs.find(value => `${value.job_id}:${value.version}` === job);
        if (!selected) throw new Error('Select an approved XML analytics job.');
        if (!fields.schema_artifact_id.trim() || !fields.xml_artifact_id.trim() || !fields.approved_by.trim()) throw new Error('Schema, XML artifact and execution identity are required.');
        const token = getCredentialProfile('DATA_JOB_EXECUTION_TOKEN');
        if (!token) throw new Error('Connect data-job execution access in Admin.');
        const definitions = JSON.parse(business);
        if (!Array.isArray(definitions)) throw new Error('Business views must be an array.');
        const binding = businessBinding || fields.schema_artifact_id.trim();
        if (definitions.length && binding !== fields.schema_artifact_id.trim()) throw new Error('View definitions belong to another schema. Reload schema fields and review the definitions.');
        const dependenciesInput = JSON.parse(dependencies);
        remember({ unknown: true, job_id: selected.job_id, job_version: selected.version, schema_artifact_id: fields.schema_artifact_id.trim(), xml_artifact_id: fields.xml_artifact_id.trim() }); submitted = true;
        const response = await dataPipelineAPI.runDefinition(selected.job_id, selected.version,
          { schema_artifact_id: fields.schema_artifact_id.trim(), xml_artifact_id: fields.xml_artifact_id.trim(),
            business_schema_artifact_id: binding, schema_prefix: fields.schema_prefix.trim(),
            schema_dependencies: dependenciesInput, business_views: definitions, constraint_policy: constraintPolicy },
          { approved_by: fields.approved_by.trim(), approval_token: token });
        const id = response.data?.run_manifest?.run_id || response.data?.run?.run_id;
        if (typeof id !== 'string' || !id) throw new Error('The submission response has no retained run identity.');
        if (current()) { remember({ run_id: id }); setReceipt(response.data); }
      }
    } catch (failure) {
      if (current()) {
        const retainedId = failure.response?.headers?.['x-depo-run-id'];
        if (submitted && retainedId) {
          remember({ run_id: retainedId });
          setError(withApiRequestId('The server retained this run. Refresh its status before submitting again.', failure));
        } else if (submitted && !confirmedSubmissionRejection(failure)) {
          setError(withApiRequestId('Submission outcome is unknown. Find the run in Data Flow history and enter its ID before retrying.', failure));
        } else {
          if (submitted) remember(null);
          setError(apiErrorMessage(failure, failure.message || 'XML analytics request failed.'));
        }
      }
    } finally { locked.current = false; if (mounted.current) setBusy(false); }
  }
  const runId = recovery?.run_id || receipt?.run_manifest?.run_id || receipt?.run?.run_id;
  const currentRun = receipt?.run_manifest || receipt?.run;
  const evidenceStatus = currentRun?.output_manifest?.evidence_status || receipt?.evidence_status;
  const Container=expanded?'section':'details';
  return <Container className="xml-analytics-loader" aria-label="Validated XML analytics loading">
    {!expanded&&<summary>Prepare and load analytics data</summary>}
    <p>Confirm the source, attach the data file you want to analyse, then choose the report fields you need.</p>
    {sources.length>0&&<div><label>Data source<select value={sourceId} disabled={busy||!!recovery} onChange={event=>{generation.current++;sourceRequest.current?.abort();setSourceId(event.target.value);setDependencies('{}');setFields(previous=>({...previous,schema_artifact_id:''}));setBusiness('[]');setBusinessBinding('');}}><option value="">Choose an imported schema</option>{sources.map(source=><option key={source.ontology_id} value={source.ontology_id}>{source.label||source.name}</option>)}</select></label><button type="button" disabled={busy||!!recovery||!sourceId} onClick={()=>perform('schema')}>Confirm source</button><p>{fields.schema_artifact_id?'Source confirmed. Attach your data file, then choose how to group and summarise its records.':'Confirm this source before adding data.'}</p></div>}
    <button type="button" disabled={busy} onClick={() => perform(false)}>Refresh loading processes</button>
    <label>Data file (XML)<input type="file" accept=".xml" disabled={busy} onChange={event => setXmlFile(event.target.files[0] || null)} /></label>
    <button type="button" disabled={busy || !xmlFile} onClick={() => perform('upload')}>Attach data file</button>
    <label>Loading process<select value={job} disabled={busy} onChange={event => { setJob(event.target.value); if (!recovery) setReceipt(null); }}>
      <option value="">Select a job</option>{jobs.map(value => <option key={`${value.job_id}:${value.version}`} value={`${value.job_id}:${value.version}`}>{value.name} ({value.version})</option>)}
    </select></label>
    {!busy&&!jobs.length&&<p role="status">A data steward needs to approve a loading process for this source before it can be used. <a href="#/data-flow">Review loading processes in Data Flow</a>.</p>}
    <details><summary>Advanced source references and load settings</summary>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
      {Object.entries({ schema_artifact_id: 'Retained XSD artifact ID', xml_artifact_id: 'Retained XML artifact ID', schema_prefix: 'Analytics schema prefix' }).map(([key, label]) => <label key={key}>{label}<input value={fields[key]} disabled={busy} onChange={event => { setFields(previous => ({ ...previous, [key]: event.target.value })); if (!recovery) setReceipt(null); }} /></label>)}
    </div>
    <label>Schema dependencies (relative path → artifact ID, JSON)<textarea value={dependencies} disabled={busy} onChange={event => { setDependencies(event.target.value); if (!recovery) setReceipt(null); }} /></label>
    </details>
    <label>Requested by<input value={fields.approved_by} disabled={busy} placeholder="Your authorised name or service identity" onChange={event=>setFields(previous=>({...previous,approved_by:event.target.value}))}/></label>
    <AnalyticsViewBuilder ontologyId={sourceId} sources={sources} disabled={busy} schemaArtifactId={fields.schema_artifact_id.trim()} onAdd={(definition, artifactId) => {
      const definitions = JSON.parse(business);
      if (!Array.isArray(definitions) || definitions.length >= 20) throw new Error('Business definitions must be an array with fewer than 20 views.');
      if (definitions.length && businessBinding && businessBinding !== artifactId) throw new Error('Clear definitions from the previous schema before adding fields.');
      if (definitions.some(value => value.name === definition.name)) throw new Error('Choose a unique view name.');
      setBusinessBinding(artifactId); setBusiness(JSON.stringify([...definitions, definition], null, 2)); if (!recovery) setReceipt(null);
    }} />
    <details><summary>Advanced validation and report definitions</summary>
    <label><input type="checkbox" checked={constraintPolicy === 'validated-source'} disabled={busy} onChange={event => { setConstraintPolicy(event.target.checked ? 'validated-source' : 'strict'); if (!recovery) setReceipt(null); }} />Validate XSD facets and fixed values against source XML during loading</label>
    <p>This option preserves source validation; it does not generate equivalent PostgreSQL facet constraints. Unsupported choices, groups, temporal policies and source-key mapping remain blocked.</p>
    <details><summary>Review or edit business definitions</summary><label>Explicit business views (JSON, optional)<textarea value={business} disabled={busy} onChange={event => { setBusiness(event.target.value); setBusinessBinding(fields.schema_artifact_id.trim()); if (!recovery) setReceipt(null); }} /></label>
    </details>
    <p>Without explicit business views, readiness is structural data loaded. Cross-entity joins, units and history policies require a separate reviewed model.</p>
    <details><summary>Business view example</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify([{ name: 'Entity count', entity_id: '{your-namespace}YourEntity', grain: 'entity-instance', group_by: [], measures: [{ name: 'count', aggregate: 'count' }] }], null, 2)}</pre><p>Use entity IDs from the retained structural model. Supported aggregates: count, sum, avg, min, max. A new business definition requires a different schema prefix.</p></details>
    </details>
    <button type="button" disabled={busy || !job || !!recovery} onClick={() => perform(true)}>Check and prepare data</button>
    {recovery && <section aria-label="Retained analytics task">
      {runId ? <><p>Retained run: {runId}</p><button type="button" disabled={busy} onClick={() => perform('refresh')}>Refresh analytics run</button>
        <button type="button" disabled={busy} onClick={() => { remember(null); setReceipt(null); setError(''); }}>Prepare another analytics task</button></> : <>
          <p>Submission is unconfirmed. Check Data Flow history before retrying.</p>
          <a href="#/data-flow">Review Data Flow history</a>
          {recovery.job_id && <p>Job {recovery.job_id} ({recovery.job_version}); schema {recovery.schema_artifact_id}; XML {recovery.xml_artifact_id}</p>}
          <label><input type="checkbox" checked={absenceConfirmed} onChange={event => setAbsenceConfirmed(event.target.checked)} />I checked history and no matching run exists</label>
          <button type="button" disabled={busy || !absenceConfirmed} onClick={() => { remember(null); setReceipt(null); setError(''); }}>Prepare another analytics task</button>
          <label>Retained analytics run ID<input value={manualRun} maxLength={200} onChange={event => setManualRun(event.target.value)} /></label>
          <button type="button" disabled={busy || !manualRun.trim()} onClick={() => perform('refresh')}>Find retained analytics run</button>
        </>}
    </section>}
    {evidenceStatus === 'pending' && <section aria-label="Analytics evidence recovery"><p>ODS data is committed. Evidence is pending; product publication remains blocked.</p><button type="button" disabled={busy || !runId} onClick={() => perform('reconcile')}>Rebuild analytics evidence</button></section>}
    {busy && <p role="status">Checking your request…</p>}
    {error && <p role="alert">{error}</p>}
    {receipt && <><p role="status">Job response: {receipt.status || 'received'}</p>{runId && <a href={pipelineRunLink(runId)}>View load run and evidence</a>}<details><summary>Technical load receipt</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 250, overflow: 'auto' }}>{JSON.stringify(receipt, null, 2)}</pre></details></>}
  </Container>;
}
