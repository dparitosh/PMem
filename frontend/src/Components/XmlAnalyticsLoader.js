import { confirmedSubmissionRejection } from '../services/workflowSubmission';
import AnalyticsViewBuilder from './AnalyticsViewBuilder';
import React, { useEffect, useRef, useState } from 'react';
import { apiClient, dataPipelineAPI } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { getCredentialProfile } from '../services/serviceAuth';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { pipelineRunLink } from '../workflows/runTracking';

const RECOVERY_KEY = 'depo-xml-analytics-recovery';
function retainedSubmission() {
  try {
    const value = JSON.parse(sessionStorage.getItem(RECOVERY_KEY));
    if (value && (value.unknown === true || typeof value.run_id === 'string')) return value;
  } catch { /* Browser storage may be unavailable. */ }
  return null;
}
export default function XmlAnalyticsLoader() {
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
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  function remember(value) {
    setRecovery(value); setAbsenceConfirmed(false);
    try { if (value) sessionStorage.setItem(RECOVERY_KEY, JSON.stringify(value)); else sessionStorage.removeItem(RECOVERY_KEY); } catch { /* Keep the current run visible if storage is unavailable. */ }
  }
  async function perform(submit) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError('');
    let submitted = false;
    try {
      if (submit === 'refresh') {
        const id = recovery?.run_id || manualRun.trim();
        if (!id) throw new Error('Enter the retained run ID from Data Flow history.');
        const response = await dataPipelineAPI.getRun(id);
        if (response.data?.run_id !== id) throw new Error('The status response does not match this run.');
        if (mounted.current) { remember({ run_id: id }); setReceipt({ status: response.data.status, run_manifest: response.data }); }
      } else if (submit === 'reconcile') {
        const id = recovery?.run_id;
        const token = getCredentialProfile('DATA_JOB_EXECUTION_TOKEN');
        if (!id || !token || !fields.approved_by.trim()) throw new Error('Enter an execution identity and connect data-job execution access.');
        const response = await dataPipelineAPI.reconcileAnalytics(id, { approved_by: fields.approved_by.trim(), approval_token: token });
        if (response.data?.run_manifest?.run_id !== id) throw new Error('The evidence response does not match this run.');
        if (mounted.current) setReceipt(response.data);
      } else if (submit === 'upload') {
        if (!xmlFile) throw new Error('Select an XML instance file.');
        const token = getCredentialProfile('INGESTION_WRITE_TOKEN');
        if (!token) throw new Error('Connect ingestion write access in Admin.');
        const body = new FormData(); body.append('file', xmlFile);
        const response = await apiClient.post(buildSemanticServiceUrl('ingestion', '/api/v1/analytics/xml-artifacts'), body,
          { headers: { Authorization: `Bearer ${token}` }, timeout: 60000 });
        if (mounted.current) { setFields(previous => ({ ...previous, xml_artifact_id: response.data.artifact.artifact_id })); if (!recovery) setReceipt(null); }
      } else if (!submit) {
        const response = await dataPipelineAPI.definitions();
        const values = response.data?.definitions;
        if (!Array.isArray(values)) throw new Error('Invalid job-definition response.');
        if (mounted.current) setJobs(values.filter(value => value.job_type === 'xml-analytics-materialize' && value.lifecycle_state === 'approved' && value.enabled));
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
        if (mounted.current) { remember({ run_id: id }); setReceipt(response.data); }
      }
    } catch (failure) {
      if (mounted.current) {
        const retainedId = failure.response?.headers?.['x-depo-run-id'];
        if (submitted && retainedId) {
          remember({ run_id: retainedId });
          setError('The server retained this run. Refresh its status before submitting again.');
        } else if (submitted && !confirmedSubmissionRejection(failure)) {
          setError('Submission outcome is unknown. Find the run in Data Flow history and enter its ID before retrying.');
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
  return <details className="depo-panel" aria-label="Validated XML analytics loading">
    <summary>Load validated XML into PostgreSQL analytics</summary>
    <p>Use retained XSD and XML artifact IDs. The approved data job validates the schema and instance, creates a versioned projection, and stores source XML with loaded rows in one transaction. Repeating the same input reconciles the existing load.</p>
    <button type="button" disabled={busy} onClick={() => perform(false)}>Load approved XML jobs</button>
    <label>XML instance file<input type="file" accept=".xml" disabled={busy} onChange={event => setXmlFile(event.target.files[0] || null)} /></label>
    <button type="button" disabled={busy || !xmlFile} onClick={() => perform('upload')}>Retain XML instance</button>
    <label>Approved XML job<select value={job} disabled={busy} onChange={event => { setJob(event.target.value); if (!recovery) setReceipt(null); }}>
      <option value="">Select a job</option>{jobs.map(value => <option key={`${value.job_id}:${value.version}`} value={`${value.job_id}:${value.version}`}>{value.name} ({value.version})</option>)}
    </select></label>
    {!jobs.length && <p>Create and approve an xml-analytics-materialize job with quality profile schema-analytics-v1 through Data Flow job definitions.</p>}
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
      {Object.entries({ schema_artifact_id: 'Retained XSD artifact ID', xml_artifact_id: 'Retained XML artifact ID', schema_prefix: 'Analytics schema prefix', approved_by: 'Execution identity' }).map(([key, label]) => <label key={key}>{label}<input value={fields[key]} disabled={busy} onChange={event => { setFields(previous => ({ ...previous, [key]: event.target.value })); if (!recovery) setReceipt(null); }} /></label>)}
    </div>
    <label>Schema dependencies (relative path → artifact ID, JSON)<textarea value={dependencies} disabled={busy} onChange={event => { setDependencies(event.target.value); if (!recovery) setReceipt(null); }} /></label>
    <AnalyticsViewBuilder disabled={busy} schemaArtifactId={fields.schema_artifact_id.trim()} onAdd={(definition, artifactId) => {
      const definitions = JSON.parse(business);
      if (!Array.isArray(definitions) || definitions.length >= 20) throw new Error('Business definitions must be an array with fewer than 20 views.');
      if (definitions.length && businessBinding && businessBinding !== artifactId) throw new Error('Clear definitions from the previous schema before adding fields.');
      if (definitions.some(value => value.name === definition.name)) throw new Error('Choose a unique view name.');
      setBusinessBinding(artifactId); setBusiness(JSON.stringify([...definitions, definition], null, 2)); if (!recovery) setReceipt(null);
    }} />
    <label><input type="checkbox" checked={constraintPolicy === 'validated-source'} disabled={busy} onChange={event => { setConstraintPolicy(event.target.checked ? 'validated-source' : 'strict'); if (!recovery) setReceipt(null); }} />Validate XSD facets and fixed values against source XML during loading</label>
    <p>This option preserves source validation; it does not generate equivalent PostgreSQL facet constraints. Unsupported choices, groups, temporal policies and source-key mapping remain blocked.</p>
    <label>Explicit business views (JSON, optional)<textarea value={business} disabled={busy} onChange={event => { setBusiness(event.target.value); setBusinessBinding(fields.schema_artifact_id.trim()); if (!recovery) setReceipt(null); }} /></label>
    <p>Without explicit business views, readiness is structural data loaded. Cross-entity joins, units and history policies require a separate reviewed model.</p>
    <details><summary>Business view example</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify([{ name: 'Entity count', entity_id: '{your-namespace}YourEntity', grain: 'entity-instance', group_by: [], measures: [{ name: 'count', aggregate: 'count' }] }], null, 2)}</pre><p>Use entity IDs from the retained structural model. Supported aggregates: count, sum, avg, min, max. A new business definition requires a different schema prefix.</p></details>
    <button type="button" disabled={busy || !job || !!recovery} onClick={() => perform(true)}>Validate and load XML</button>
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
    {busy && <p role="status">Processing XML analytics request…</p>}
    {error && <p role="alert">{error}</p>}
    {receipt && <><p role="status">Job response: {receipt.status || 'received'}</p>{runId && <a href={pipelineRunLink(runId)}>View load run and evidence</a>}<pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 250, overflow: 'auto' }}>{JSON.stringify(receipt, null, 2)}</pre></>}
  </details>;
}
