import React, { useCallback, useEffect, useRef, useState } from 'react';
import { IxButton } from '@siemens/ix-react';
import RegistryWidget from '../widgets/RegistryWidget';
import { apiClient, dataPipelineAPI } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { useOntologies } from '../contexts/OntologyContext';
import { readProductCollection, PRODUCT_REFRESH_MS, PRODUCT_CHANGED_EVENT } from '../services/productService';
import { productDraftFromRun } from '../services/analyticsProductDraft';
import SchemaProductPublisher from '../Components/SchemaProductPublisher';
import FirstProductGuide from '../Components/FirstProductGuide';

const columns = [
  { field: 'product_id', headerName: 'Product ID', flex: 1.2 },
  { field: 'name', flex: 1.5 }, { field: 'version', width: 110 },
  { field: 'domain', flex: 1 }, { field: 'owner', flex: 1 },
  { field: 'lifecycle_state', headerName: 'Lifecycle', flex: 1 },
  { field: 'status', headerName: 'Delivery status', flex: 1.2 },
];

export default function DataProductsPage({ mode = 'products' }) {
  const catalog = mode === 'catalog';
  const title = catalog ? 'Data Catalog' : 'Data Products';
  const { ontologies, error: ontologyError, warning: ontologyWarning, loading: ontologyLoading } = useOntologies();
  const drafts = (ontologies || []).filter(ontology => ontology.data_product_draft?.contract);
  const [selectedDraft, setSelectedDraft] = useState('');
  const draft = drafts.find(ontology => ontology.ontology_id === selectedDraft);
  const [state, setState] = useState({ loading: true, rows: [], error: '', warning: '' });
  const [selected, setSelected] = useState('');
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState('');
  const [detailLoading, setDetailLoading] = useState(false);
  const [runDraft, setRunDraft] = useState(null);
  const [runDraftError, setRunDraftError] = useState('');
  const listRequest = useRef(null);
  const detailRequest = useRef(null);
  const selectedRef = useRef('');
  const service = catalog ? 'catalog' : 'dataProducts';
  const path = catalog ? '/api/v1/catalog/products' : '/api/v1/data-products';

  const load = useCallback(async (background = false) => {
    if (background === true && listRequest.current) return;
    listRequest.current?.abort();
    if (background !== true) {
    detailRequest.current?.abort();
    setDetail(null); setDetailError(''); setDetailLoading(false); setSelected(''); selectedRef.current = '';
    }
    const controller = new AbortController(); listRequest.current = controller;
    let timedOut = false;
    const deadline = setTimeout(() => { timedOut = true; controller.abort(); }, 60000);
    if (background !== true) setState({ loading: true, rows: [], error: '', total: null });
    try {
      const collection = await readProductCollection(service, controller.signal);
      if (controller.signal.aborted) return;
      if (background === true) {
        const key = selectedRef.current;
        if (key && collection.rows.some(row => (catalog ? row.product_id : `${row.product_id}:${row.version}`) === key)) {
          showDetail(key);
        } else {
          detailRequest.current?.abort();
          setDetail(null); setDetailError(''); setDetailLoading(false);
          setSelected(''); selectedRef.current = '';
        }
      }
      setState({ loading: false, rows: collection.rows, total: collection.total, error: '', warning: collection.warning });
    } catch (error) {
      if (listRequest.current !== controller || (controller.signal.aborted && !timedOut)) return;
      detailRequest.current?.abort();
      setDetail(null); setDetailError(''); setDetailLoading(false);
      setSelected(''); selectedRef.current = '';
      setState({ loading: false, rows: [], error: timedOut ? 'Product-list retrieval exceeded one minute. Retry or check service response times.' : apiErrorMessage(error, 'Product service request failed.'), warning: '' });
    } finally {
      clearTimeout(deadline);
      if (listRequest.current === controller) listRequest.current = null;
    }
  }, [service, path, catalog]);

  useEffect(() => {
    load();
    const interval = window.setInterval(() => { if (!document.hidden) load(true); }, PRODUCT_REFRESH_MS);
    window.addEventListener(PRODUCT_CHANGED_EVENT, load);
    window.addEventListener('depo:credentials-changed', load);
    window.addEventListener('depo:credentials-cleared', load);
    return () => {
      listRequest.current?.abort(); detailRequest.current?.abort();
      window.clearInterval(interval);
      window.removeEventListener(PRODUCT_CHANGED_EVENT, load);
      window.removeEventListener('depo:credentials-changed', load);
      window.removeEventListener('depo:credentials-cleared', load);
    };
  }, [load]);

  useEffect(() => {
    let active = true;
    let sequence = 0;
    let request = null;
    const loadRunDraft = async () => {
      const current = ++sequence;
      request?.abort();
      const controller = new AbortController(); request = controller;
      setRunDraft(null); setRunDraftError('');
      const runId = new URLSearchParams(window.location.hash.split('?')[1] || '').get('run_id');
      if (catalog || !runId) return;
      try {
        const response = await dataPipelineAPI.getRun(runId, { signal: controller.signal, timeout: 15000 });
        const run = response?.data?.data || response?.data || response;
        if (run?.run_id !== runId) throw new Error('Pipeline returned a different run identity.');
        const value = productDraftFromRun(run);
        if (active && current === sequence) setRunDraft(value);
      } catch (error) { if (active && current === sequence) setRunDraftError(apiErrorMessage(error, 'Retained run evidence is unavailable.')); }
    };
    const refresh = () => { loadRunDraft(); };
    loadRunDraft();
    window.addEventListener('hashchange', refresh);
    window.addEventListener('depo:credentials-changed', refresh);
    window.addEventListener('depo:credentials-cleared', refresh);
    return () => { active = false; request?.abort(); window.removeEventListener('hashchange', refresh); window.removeEventListener('depo:credentials-changed', refresh); window.removeEventListener('depo:credentials-cleared', refresh); };
  }, [catalog]);

  async function showDetail(key) {
    selectedRef.current = key;
    detailRequest.current?.abort(); setSelected(key); setDetail(null); setDetailError('');
    if (!key) { setDetailLoading(false); return; }
    const controller = new AbortController(); detailRequest.current = controller; setDetailLoading(true);
    try {
      const response = await apiClient.get(buildSemanticServiceUrl(service, `${path}/${encodeURIComponent(key)}`), { signal: controller.signal, timeout: 15000 });
      if (!controller.signal.aborted) setDetail(response.data);
    } catch (error) {
      if (!controller.signal.aborted) setDetailError(apiErrorMessage(error, 'Product details are unavailable.'));
    } finally {
      if (!controller.signal.aborted) setDetailLoading(false);
    }
  }

  const keys = [...new Set(state.rows.map(row => catalog ? row.product_id : `${row.product_id}:${row.version}`))];
  return <section className="depo-panel" aria-label={title}>
    <AgentProposalPanel title="Product governance recommendations" agentIds={['data-product-governor']} context={{ page: catalog ? 'data-catalog' : 'data-products', product_ids: state.rows.map(row => row.product_id).slice(0, 20) }} />
    <div className="depo-panel__header"><h2>{title}</h2><IxButton onClick={load} disabled={state.loading}>Refresh</IxButton></div>
    <p>{catalog ? 'Browse governed product versions, ownership and lifecycle.' : 'Browse retained product packages and their catalog delivery status.'}</p>
    {state.loading && <p role="status">Loading products…</p>}
    {state.error && <div role="alert" className="depo-alert depo-alert--warning">{state.error}</div>}
    {state.warning && <div role="alert" className="depo-alert depo-alert--warning">{state.warning}</div>}
    {!catalog && <section aria-label="Pipeline product evidence">
      <h3>Data Flow evidence</h3><p>Select a completed run in <a href="#/data-flow">Data Flow</a> to create a draft from its retained artifacts. Graph publication and product packaging are separate approved operations.</p>
      {runDraftError && <p role="alert">{runDraftError}</p>}
      {runDraft && <SchemaProductPublisher draft={runDraft} />}
    </section>}
    {!catalog && state.rows.some(row => row.status === 'pending_catalog_registration') && <p role="status">Some packages are retained but catalog registration is pending. Inspect their delivery details; a retained package does not guarantee a catalog entry.</p>}
    {!state.loading && !state.error && !state.warning && state.rows.length === 0 && <FirstProductGuide catalog={catalog} />}
    {!catalog && <section aria-label="Schema design drafts">
      <h3>Schema design drafts ({drafts.length})</h3>
      {ontologyLoading && <p role="status">Loading ontology draft metadata…</p>}
      {(ontologyError || ontologyWarning) && <div role="alert">{ontologyError || ontologyWarning}</div>}
      <p>Retained conversion evidence is a draft, not a published warehouse. Publication requires an approved semantic release and data-product steward approval.</p>
      <select aria-label="Schema design draft" value={draft ? selectedDraft : ''} onChange={event => setSelectedDraft(event.target.value)}>
        <option value="">Select imported schema draft</option>
        {drafts.map(ontology => <option key={ontology.ontology_id} value={ontology.ontology_id}>{ontology.label}</option>)}
      </select>
      {draft && <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 350, overflow: 'auto' }}>{JSON.stringify(draft.data_product_draft, null, 2)}</pre>}
      <SchemaProductPublisher draft={draft?.data_product_draft} />
      {!ontologyLoading && !ontologyError && !ontologyWarning && !drafts.length && <p>No retained schema-design draft metadata is available. Older imports may need reimporting with this release to retain their evidence references.</p>}
    </section>}
    <RegistryWidget title={`${title} (${state.total ?? '—'} total; ${state.rows.length} loaded)`} rows={state.rows} columns={columns} height={400} />
    <label htmlFor="product-detail">Product details and versions</label>
    <select style={{ color: 'var(--ui-text)', background: 'var(--ui-surface)', border: '1px solid var(--ui-border)', padding: 8, margin: 8 }} id="product-detail" value={selected} onChange={event => showDetail(event.target.value)}>
      <option value="">Select a product</option>{keys.map(key => <option key={key} value={key}>{key}</option>)}
    </select>
    {detailLoading && <p role="status">Loading product details…</p>}
    {detailError && <div role="alert">{detailError}</div>}
    {detail && <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 450, overflow: 'auto', color: 'var(--ui-text)' }}>{JSON.stringify(detail, null, 2)}</pre>}
  </section>;
}
import AgentProposalPanel from '../Components/AgentProposalPanel';
