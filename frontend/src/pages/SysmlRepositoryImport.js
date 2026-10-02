import React, { useState, useEffect } from 'react';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { getCredentialProfile } from '../services/serviceAuth';
import { pipelineRunLink, requireRunManifest } from '../workflows/runTracking';
import useMountedRef from '../hooks/useMountedRef';
import { apiErrorMessage } from '../utils/apiErrorMessage';
export default function SysmlRepositoryImport() {
  const mounted = useMountedRef();
  const [configuration, setConfiguration] = useState(null);
  const [token, setToken] = useState('');
  useEffect(() => {
    const clear = () => setToken('');
    window.addEventListener('depo:credentials-cleared', clear);
    return () => window.removeEventListener('depo:credentials-cleared', clear);
  }, []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const url = path => buildSemanticServiceUrl('ingestion', `/api/v1/sysml-v2/${path}`);
  const check = async () => {
    setBusy(true); setError(''); setConfiguration(null);
    try { const response = await apiClient.get(url('status')); if (mounted.current) setConfiguration(response.data); }
    catch (failure) { if (mounted.current) setError(apiErrorMessage(failure)); }
    finally { if (mounted.current) setBusy(false); }
  };
  const start = async () => {
    const key = token.trim() || getCredentialProfile('DATA_JOB_EXECUTION_TOKEN');
    if (!key) { setError('Enter DATA_JOB_EXECUTION_TOKEN in API access or below.'); return; }
    setBusy(true); setError(''); setResult(null);
    try {
      const response = await apiClient.post(url('import-commit'), {}, { headers: { Authorization: `Bearer ${key}` }, timeout: 300000 });
      requireRunManifest(response.data);
      if (mounted.current) { setResult(response.data); setToken(''); }
    } catch (failure) { if (mounted.current) setError(apiErrorMessage(failure)); }
    finally { if (mounted.current) setBusy(false); }
  };
  const ready = configuration?.enabled && configuration?.configured && configuration?.project_configured && configuration?.commit_configured;
  return <section className="depo-page">
    <h2>SysML v2 repository import</h2>
    <p>Configure SYSML_V2_API_ENABLED, SYSML_V2_API_BASE_URL, SYSML_V2_API_TOKEN, SYSML_V2_PROJECT_ID and SYSML_V2_COMMIT_ID in the server environment, then restart ingestion. This imports the configured commit into a governed data job; graph publication is a separate approval step.</p>
    <button type="button" onClick={check} disabled={busy}>Check repository configuration</button>
    {configuration && <p>Repository: {configuration.base_url || 'not configured'} · Project: {configuration.project_id || 'not configured'} · Commit: {configuration.commit_id || 'not configured'} · {ready ? 'Configuration complete; connectivity is checked during import.' : 'Complete server configuration before importing.'}</p>}
    <label>Execution key (optional if entered in API access)<input type="password" autoComplete="off" value={token} onChange={event => setToken(event.target.value)} /></label>
    <button type="button" onClick={start} disabled={busy || !ready}>{busy ? 'Working...' : 'Import configured commit'}</button>
    {error && <p role="alert">{error}</p>}
    {result && <p role="status">Job: {result.run_manifest?.run_id || 'No run ID returned'} · Status: {result.run_manifest?.status || result.status || 'received'}. <a href={pipelineRunLink(result.run_manifest.run_id)}>Open Data Flow to review the durable run and approval steps.</a></p>}
  </section>;
}
