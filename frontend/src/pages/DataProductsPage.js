import React, { useCallback, useEffect, useRef, useState } from 'react';
import { IxButton } from '@siemens/ix-react';
import RegistryWidget from '../widgets/RegistryWidget';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { useOntologies } from '../contexts/OntologyContext';
import { loadProductCollection } from '../services/productCollection';

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
  const listRequest = useRef(null);
  const detailRequest = useRef(null);
  const service = catalog ? 'catalog' : 'dataProducts';
  const path = catalog ? '/api/v1/catalog/products' : '/api/v1/data-products';

  const load = useCallback(async () => {
    listRequest.current?.abort();
    detailRequest.current?.abort();
    setDetail(null); setDetailError(''); setDetailLoading(false); setSelected('');
    const controller = new AbortController(); listRequest.current = controller;
    let timedOut = false;
    const deadline = setTimeout(() => { timedOut = true; controller.abort(); }, 60000);
    setState({ loading: true, rows: [], error: '' });
    try {
      const collection = await loadProductCollection(params => apiClient.get(buildSemanticServiceUrl(service, path), { signal: controller.signal, params, timeout: 15000 }), controller.signal);
      if (controller.signal.aborted) return;
      setState({ loading: false, rows: collection.rows, error: '', warning: collection.warning });
    } catch (error) {
      if (listRequest.current !== controller || (controller.signal.aborted && !timedOut)) return;
      setState({ loading: false, rows: [], error: timedOut ? 'Product-list retrieval exceeded one minute. Retry or check service response times.' : apiErrorMessage(error, 'Product service request failed.'), warning: '' });
    } finally {
      clearTimeout(deadline);
    }
  }, [service, path]);

  useEffect(() => {
    load();
    window.addEventListener('depo:credentials-changed', load);
    window.addEventListener('depo:credentials-cleared', load);
    return () => {
      listRequest.current?.abort(); detailRequest.current?.abort();
      window.removeEventListener('depo:credentials-changed', load);
      window.removeEventListener('depo:credentials-cleared', load);
    };
  }, [load]);

  async function showDetail(key) {
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
    <div className="depo-panel__header"><h2>{title}</h2><IxButton onClick={load} disabled={state.loading}>Refresh</IxButton></div>
    <p>{catalog ? 'Browse governed product versions, ownership and lifecycle.' : 'Browse retained product packages and their catalog delivery status.'}</p>
    {state.loading && <p role="status">Loading products…</p>}
    {state.error && <div role="alert" className="depo-alert depo-alert--warning">{state.error}</div>}
    {state.warning && <div role="alert" className="depo-alert depo-alert--warning">{state.warning}</div>}
    {!state.loading && !state.error && state.rows.length === 0 && <p>No products are registered yet. Creating an ontology does not publish a data product.</p>}
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
      {!ontologyLoading && !ontologyError && !ontologyWarning && !drafts.length && <p>No retained schema-design draft metadata is available. Older imports may need reimporting with this release to retain their evidence references.</p>}
    </section>}
    <RegistryWidget title={`${title} (${state.rows.length})`} rows={state.rows} columns={columns} height={400} />
    <label htmlFor="product-detail">Product details and versions</label>
    <select style={{ color: 'var(--ui-text)', background: 'var(--ui-surface)', border: '1px solid var(--ui-border)', padding: 8, margin: 8 }} id="product-detail" value={selected} onChange={event => showDetail(event.target.value)}>
      <option value="">Select a product</option>{keys.map(key => <option key={key} value={key}>{key}</option>)}
    </select>
    {detailLoading && <p role="status">Loading product details…</p>}
    {detailError && <div role="alert">{detailError}</div>}
    {detail && <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 450, overflow: 'auto', color: 'var(--ui-text)' }}>{JSON.stringify(detail, null, 2)}</pre>}
  </section>;
}
