import React, { useEffect, useRef, useState } from 'react';
import { IxButton } from '@siemens/ix-react';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { getCredentialProfile, publicationRecoveryScope } from '../services/serviceAuth';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { publicationFromDraft, isDefinitivePublicationRejection } from '../services/analyticsProductDraft';
import { productChanged } from '../services/productService';

const labels = { product_id: 'Product ID', name: 'Product name', version: 'New product version (e.g. 1.0.0)', owner: 'Owner',
  steward: 'Steward', classification: 'Classification', approved_by: 'Approver', asset_id: 'Approved semantic asset ID', release_version: 'Approved semantic release version' };

export default function SchemaProductPublisher({ draft, onPublished }) {
  const [fields, setFields] = useState({});
  const [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');
  const [receipt, setReceipt] = useState(null);
  const request = useRef(null);
  const pending = useRef(null);
  const pendingDraft = useRef(null);
  const pendingStorageKey = useRef(null);
  const recoveryScope = publicationRecoveryScope();
  const initialRecoveryScope = useRef(recoveryScope);
  const storageKey = `depo:pending-publication:${JSON.stringify([recoveryScope, draft || null])}`;
  const [source, setSource] = useState(null);
  const [dependencies, setDependencies] = useState([]);
  const [paths, setPaths] = useState('');
  const [converted, setConverted] = useState(null);
  const [sourceChanged, setSourceChanged] = useState(false);
  useEffect(() => {
    if (pending.current) return;
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
      if (saved?.scope === recoveryScope && saved?.payload && saved?.draft && saved?.fields) {
        pending.current = saved.payload; pendingDraft.current = saved.draft;
        pendingStorageKey.current = storageKey;
        setFields(saved.fields); setPreview({ valid: true }); setReceipt(null);
        setError('Recovered an uncertain publication. Retry the same request to reconcile its outcome.');
        return;
      }
    } catch {
      setError('Pending publication recovery failed. Check the retained product before publishing again.');
      return;
    }
    request.current?.abort(); request.current = null; pending.current = null;
    setFields({ name: draft?.name || '', version: '1.0.0', classification: 'internal' });
    setPreview(null); setReceipt(null); setError(''); setConverted(null); setBusy(false);
    setSourceChanged(false); setSource(null); setDependencies([]); setPaths('');
  }, [draft]);
  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    const reset = () => {
      request.current?.abort(); request.current = null;
      // Credential expiry does not cancel an already accepted server write.
      setPreview(pending.current ? { valid: true } : null); setReceipt(null); setBusy(false);
      setError(pending.current ? 'Reconnect access, then retry the same publication to reconcile its outcome.' : 'Credentials changed. Validate the contract again after reconnecting.');
    };
    for (const event of ['depo:credentials-cleared', 'depo:credentials-changed', 'depo:session-expired']) window.addEventListener(event, reset);
    return () => {
      for (const event of ['depo:credentials-cleared', 'depo:credentials-changed', 'depo:session-expired']) window.removeEventListener(event, reset);
    };
  }, []);
  const activeDraft = pending.current ? pendingDraft.current : converted?.data_product_draft || (sourceChanged ? null : draft);
  function invalidateInspection() {
    setSourceChanged(true); setConverted(null); setPreview(null); setReceipt(null); setError('');
  }
  async function perform(action) {
    if (busy || request.current) return;
    const controller = new AbortController(); request.current = controller; setBusy(true); setError('');
    try {
      if (publicationRecoveryScope() !== initialRecoveryScope.current) throw new Error('Service connection changed. Reopen publication before continuing.');
      const profile = action === 'inspect' ? 'INGESTION_WRITE_TOKEN' : 'DATA_PRODUCT_APPROVAL_TOKEN';
      const token = getCredentialProfile(profile);
      if (!token) throw new Error(`Connect in Admin or test and apply ${profile} before continuing.`);
      const headers = { Authorization: `Bearer ${token}` };
      if (action === 'inspect') {
        if (!source) throw new Error('Select the root XSD file.');
        const relative = paths.split('\n').map(value => value.trim()).filter(Boolean);
        if (relative.length !== dependencies.length) throw new Error('Enter one relative path per dependency file in the displayed order.');
        const body = new FormData(); body.append('file', source);
        dependencies.forEach(file => body.append('dependencies', file));
        body.append('dependency_paths', JSON.stringify(relative));
        const response = await apiClient.post(buildSemanticServiceUrl('ingestion', '/api/v1/schema-conversions/inspect'), body,
          { headers, signal: controller.signal, timeout: 180000 });
        if (controller.signal.aborted) return;
        setConverted(response.data); setFields(previous => ({ ...previous, name: response.data.data_product_draft?.name || previous.name }));
        pending.current = null; setPreview(null); setReceipt(null);
      } else {
        const payload = pending.current || publicationFromDraft(activeDraft, fields, `schema-product-${Date.now()}-${Math.random().toString(36).slice(2)}`);
        if (action === 'publish') {
          if (!preview?.valid) throw new Error('Validate the publication contract before publishing.');
          // Save before sending; credentials are never included in this record.
          sessionStorage.setItem(pendingStorageKey.current || storageKey,
            JSON.stringify({ scope: recoveryScope, payload, draft: activeDraft, fields }));
          pendingStorageKey.current = pendingStorageKey.current || storageKey;
          pending.current = payload;
          pendingDraft.current = activeDraft;
        }
        const response = await apiClient.post(buildSemanticServiceUrl('dataProducts', `/api/v1/data-products/${action === 'publish' ? 'publish' : 'preview'}`), payload,
          { headers, signal: controller.signal, timeout: 60000 });
        if (controller.signal.aborted) return;
        if (action === 'publish') {
          sessionStorage.removeItem(pendingStorageKey.current); pendingStorageKey.current = null;
          pending.current = null; pendingDraft.current = null;
          setReceipt(response.data); productChanged(); onPublished?.();
        }
        else setPreview(response.data);
      }
    } catch (failure) {
      if (!controller.signal.aborted && action === 'publish' && isDefinitivePublicationRejection(failure)) {
        sessionStorage.removeItem(pendingStorageKey.current); pendingStorageKey.current = null;
        pending.current = null; setPreview(null);
      }
      if (!controller.signal.aborted) setError(apiErrorMessage(failure, failure.message || 'Request failed.'));
    } finally { if (request.current === controller) { request.current = null; if (!controller.signal.aborted) setBusy(false); } }
  }
  const pipeline = draft?.product_kind === 'pipeline-evidence';
  return <section aria-label={pipeline ? 'Pipeline evidence publication' : 'Schema analytics publication'}>
    <h3>{pipeline ? 'Publish retained pipeline evidence' : 'Publish schema design evidence'}</h3>
    <p>{pipeline ? 'Package the retained run artifacts for steward review. Job completion does not certify their quality.' : 'This package contains a review-only schema plan. It does not create warehouse tables or certify business metrics.'} The service verifies the referenced approved semantic release during publication.</p>
    {!pipeline && <details><summary>Inspect an XSD with dependency files</summary>
      <label>Root XSD <input type="file" accept=".xsd" disabled={busy || !!pending.current} onChange={event => { invalidateInspection(); setSource(event.target.files[0] || null); }} /></label>
      <label>Dependency XSD files <input type="file" accept=".xsd" multiple disabled={busy || !!pending.current} onChange={event => { invalidateInspection(); setDependencies(Array.from(event.target.files)); }} /></label>
      <p>Selected dependency order: {dependencies.map(file => file.name).join(', ') || 'None'}</p>
      <label>Relative paths, one per file (e.g. types/Part.xsd)<textarea value={paths} disabled={busy || !!pending.current} onChange={event => { invalidateInspection(); setPaths(event.target.value); }} /></label>
      <IxButton disabled={busy || !!pending.current} onClick={() => perform('inspect')}>Inspect schema set</IxButton>
    </details>}
    {sourceChanged && !activeDraft && <p role="status">Source selection changed. Inspect the schema set again before validating or publishing.</p>}
    {activeDraft && <>
      <p>Readiness: {activeDraft.analytics_readiness || 'Requires review'}; quality: {activeDraft.quality_status || 'Not assessed'}</p>
      {converted?.analytics_schema_plan?.ddl_blockers?.length > 0 && <div role="alert">Schema materialization blockers: {converted.analytics_schema_plan.ddl_blockers.join('; ')}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 12 }}>
        {Object.entries(labels).map(([key, label]) => <label key={key}>{label}<input style={{ width: '100%' }} value={fields[key] || ''} disabled={busy || !!pending.current}
          onChange={event => { setFields(previous => ({ ...previous, [key]: event.target.value })); setPreview(null); setReceipt(null); }} /></label>)}
      </div>
      <IxButton disabled={busy || !!pending.current} onClick={() => perform('preview')}>Validate publication contract</IxButton>
      <IxButton disabled={busy || !preview?.valid || !!receipt} onClick={() => perform('publish')}>{pending.current ? 'Retry same publication' : 'Approve and publish evidence'}</IxButton>
      {preview && <p role="status">{preview.valid ? 'Contract valid. Steward approval is still required.' : preview.errors?.join('; ')}</p>}
      {receipt && <p role="status">{receipt.product_id}@{receipt.version}: {receipt.status}. Pending catalog delivery retries through the outbox worker.</p>}
      {pending.current && !receipt && <p>Publication outcome may be uncertain. Retry preserves the exact payload and request identity. Do not change the version to work around an unknown outcome.</p>}
    </>}
    {error && <div role="alert">{error}</div>}
  </section>;
}
