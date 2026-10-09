import React, { useEffect, useRef, useState } from 'react';
import { apiClient, dataPipelineAPI } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { getCredentialProfile } from '../services/serviceAuth';
import { apiErrorMessage } from '../utils/apiErrorMessage';

export default function XmlAnalyticsLoader() {
  const [jobs, setJobs] = useState([]);
  const [job, setJob] = useState('');
  const [fields, setFields] = useState({ schema_artifact_id: '', xml_artifact_id: '', schema_prefix: 'depo_analytics', approved_by: '' });
  const [dependencies, setDependencies] = useState('{}');
  const [business, setBusiness] = useState('[]');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState(null);
  const [xmlFile, setXmlFile] = useState(null);
  const mounted = useRef(true);
  const locked = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function perform(submit) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError('');
    try {
      if (submit === 'upload') {
        if (!xmlFile) throw new Error('Select an XML instance file.');
        const token = getCredentialProfile('INGESTION_WRITE_TOKEN');
        if (!token) throw new Error('Connect ingestion write access in Admin.');
        const body = new FormData(); body.append('file', xmlFile);
        const response = await apiClient.post(buildSemanticServiceUrl('ingestion', '/api/v1/analytics/xml-artifacts'), body,
          { headers: { Authorization: `Bearer ${token}` }, timeout: 60000 });
        if (mounted.current) { setFields(previous => ({ ...previous, xml_artifact_id: response.data.artifact.artifact_id })); setReceipt(null); }
      } else if (!submit) {
        const response = await dataPipelineAPI.definitions();
        const values = response.data?.definitions;
        if (!Array.isArray(values)) throw new Error('Invalid job-definition response.');
        if (mounted.current) setJobs(values.filter(value => value.job_type === 'xml-analytics-materialize' && value.lifecycle_state === 'approved' && value.enabled));
      } else {
        setReceipt(null);
        const selected = jobs.find(value => `${value.job_id}:${value.version}` === job);
        if (!selected) throw new Error('Select an approved XML analytics job.');
        if (!fields.schema_artifact_id.trim() || !fields.xml_artifact_id.trim() || !fields.approved_by.trim()) throw new Error('Schema, XML artifact and execution identity are required.');
        const token = getCredentialProfile('DATA_JOB_EXECUTION_TOKEN');
        if (!token) throw new Error('Connect data-job execution access in Admin.');
        const response = await dataPipelineAPI.runDefinition(selected.job_id, selected.version,
          { schema_artifact_id: fields.schema_artifact_id.trim(), xml_artifact_id: fields.xml_artifact_id.trim(),
            schema_prefix: fields.schema_prefix.trim(), schema_dependencies: JSON.parse(dependencies), business_views: JSON.parse(business) },
          { approved_by: fields.approved_by.trim(), approval_token: token });
        if (mounted.current) setReceipt(response.data);
      }
    } catch (failure) {
      if (mounted.current) setError(apiErrorMessage(failure, failure.message || 'XML analytics request failed. Check Data Flow runs before retrying.'));
    } finally { locked.current = false; if (mounted.current) setBusy(false); }
  }
  const runId = receipt?.run_manifest?.run_id || receipt?.run?.run_id;
  return <details className="depo-panel" aria-label="Validated XML analytics loading">
    <summary>Load validated XML into PostgreSQL analytics</summary>
    <p>Use retained XSD and XML artifact IDs. The approved data job validates the schema and instance, creates a versioned projection, and stores source XML with loaded rows in one transaction. Repeating the same input reconciles the existing load.</p>
    <button type="button" disabled={busy} onClick={() => perform(false)}>Load approved XML jobs</button>
    <label>XML instance file<input type="file" accept=".xml" disabled={busy} onChange={event => setXmlFile(event.target.files[0] || null)} /></label>
    <button type="button" disabled={busy || !xmlFile} onClick={() => perform('upload')}>Retain XML instance</button>
    <label>Approved XML job<select value={job} disabled={busy} onChange={event => { setJob(event.target.value); setReceipt(null); }}>
      <option value="">Select a job</option>{jobs.map(value => <option key={`${value.job_id}:${value.version}`} value={`${value.job_id}:${value.version}`}>{value.name} ({value.version})</option>)}
    </select></label>
    {!jobs.length && <p>Create and approve an xml-analytics-materialize job with quality profile schema-analytics-v1 through Data Flow job definitions.</p>}
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
      {Object.entries({ schema_artifact_id: 'Retained XSD artifact ID', xml_artifact_id: 'Retained XML artifact ID', schema_prefix: 'Analytics schema prefix', approved_by: 'Execution identity' }).map(([key, label]) => <label key={key}>{label}<input value={fields[key]} disabled={busy} onChange={event => { setFields(previous => ({ ...previous, [key]: event.target.value })); setReceipt(null); }} /></label>)}
    </div>
    <label>Schema dependencies (relative path → artifact ID, JSON)<textarea value={dependencies} disabled={busy} onChange={event => { setDependencies(event.target.value); setReceipt(null); }} /></label>
    <label>Explicit business views (JSON, optional)<textarea value={business} disabled={busy} onChange={event => { setBusiness(event.target.value); setReceipt(null); }} /></label>
    <p>Without explicit business views, readiness is structural data loaded. Cross-entity joins, units and history policies require a separate reviewed model.</p>
    <details><summary>Business view example</summary><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify([{ name: 'Entity count', entity_id: '{your-namespace}YourEntity', grain: 'entity-instance', group_by: [], measures: [{ name: 'count', aggregate: 'count' }] }], null, 2)}</pre><p>Use entity IDs from the retained structural model. Supported aggregates: count, sum, avg, min, max. A new business definition requires a different schema prefix.</p></details>
    <button type="button" disabled={busy || !job} onClick={() => perform(true)}>Validate and load XML</button>
    {busy && <p role="status">Processing XML analytics request…</p>}
    {error && <p role="alert">{error}</p>}
    {receipt && <><p role="status">Job response: {receipt.status || 'received'}</p>{runId && <a href={`#/data-flow?run_id=${encodeURIComponent(runId)}`}>View load run and evidence</a>}<pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 250, overflow: 'auto' }}>{JSON.stringify(receipt, null, 2)}</pre></>}
  </details>;
}
