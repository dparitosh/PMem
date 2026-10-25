import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { IxButton } from '@siemens/ix-react';
import RegistryWidget from '../widgets/RegistryWidget';
import { apiClient, dataPipelineAPI } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import { useOntologies } from '../contexts/OntologyContext';
import { readProductCollection, PRODUCT_REFRESH_MS, PRODUCT_CHANGED_EVENT } from '../services/productService';
import { productDraftFromRun, productDraftFromOntology } from '../services/analyticsProductDraft';
import SchemaProductPublisher from '../Components/SchemaProductPublisher';
import FirstProductGuide from '../Components/FirstProductGuide';
import XmlAnalyticsLoader from '../Components/XmlAnalyticsLoader';
import IngestedDataInventory from '../Components/IngestedDataInventory';
import AnalyticsSchemaReview from '../Components/AnalyticsSchemaReview';
import ProductEvidenceDetails from '../Components/ProductEvidenceDetails';
import EvidenceProductOptions from '../Components/EvidenceProductOptions';
import './DataProductsPage.css';
import DataWorkspace, {DataJourney} from '../Components/DataWorkspace';

const columns = [
  { field: 'product_id', headerName: 'Product ID', flex: 1.2 },
  { field: 'name', flex: 1.5 }, { field: 'version', width: 110 },
  { field: 'domain', flex: 1 }, { field: 'owner', flex: 1 },
  { field: 'product_kind', headerName: 'Evidence type', flex: 1.4, valueFormatter: ({value}) => ({'schema-design-evidence':'Structural analytics','pipeline-evidence':'Pipeline evidence','ontology-evidence':'Ontology evidence'}[value] || value || 'Not recorded') },
  { field: 'lifecycle_state', headerName: 'Lifecycle', flex: 1 },
  { field: 'status', headerName: 'Delivery status', flex: 1.2 },
];

export default function DataProductsPage({ mode = 'products' }) {
  const catalog = mode === 'catalog';
  const [workspace,setWorkspace]=useState(()=>{const query=new URLSearchParams(window.location.hash.split('?')[1]||'');return mode==='catalog'?'sources':query.has('view')||query.has('run_id')?'create':'library';});
  const title = catalog ? 'Data Catalog' : 'Data Products';
  const { ontologies, error: ontologyError, warning: ontologyWarning, loading: ontologyLoading } = useOntologies();
  const drafts = (ontologies || []).filter(ontology => ontology.data_product_draft?.contract);
  const [selectedDraft, setSelectedDraft] = useState('');
  const draft = drafts.find(ontology => ontology.ontology_id === selectedDraft);
  const selectedProductDraft = useMemo(() => productDraftFromOntology(draft), [draft]);
  const [state, setState] = useState({ loading: true, rows: [], error: '', warning: '' });
  const [selected, setSelected] = useState('');
  const [filter,setFilter] = useState('');
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState('');
  const [detailLoading, setDetailLoading] = useState(false);
  const [runDraft, setRunDraft] = useState(null);
  const [runDraftError, setRunDraftError] = useState('');
  const listRequest = useRef(null);
  const detailRequest = useRef(null);
  const selectedRef = useRef('');
  const structuralRef=useRef(null),pipelineRef=useRef(null);
  const revealEvidence=kind=>{
    const target=kind==='structural'?structuralRef.current:pipelineRef.current;
    setWorkspace('create');
    if(target){target.open=true;}
  };
  const service = catalog ? 'catalog' : 'dataProducts';
  const path = catalog ? '/api/v1/catalog/products' : '/api/v1/data-products';

  useEffect(()=>{
    const query=new URLSearchParams(window.location.hash.split('?')[1]||'');
    setWorkspace(catalog?'sources':query.has('view')||query.has('run_id')?'create':'library');
    if(catalog)return;
    const reveal=()=>{const view=new URLSearchParams(window.location.hash.split('?')[1]||'').get('view');if(['structural','pipeline'].includes(view))revealEvidence(view);};
    reveal();window.addEventListener('hashchange',reveal);
    return()=>window.removeEventListener('hashchange',reveal);
  },[catalog]);

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
          showDetail(key, true);
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

  async function showDetail(key, background = false) {
    selectedRef.current = key;
    detailRequest.current?.abort(); setSelected(key); if (!background) setDetail(null); setDetailError('');
    if (!key) { setDetailLoading(false); return; }
    const controller = new AbortController(); detailRequest.current = controller; setDetailLoading(true);
    try {
      const response = await apiClient.get(buildSemanticServiceUrl(service, `${path}/${encodeURIComponent(key)}`), { signal: controller.signal, timeout: 15000 });
      if (!controller.signal.aborted) setDetail(response.data);
    } catch (error) {
      if (!controller.signal.aborted) {
        setDetail(null);
        setDetailError(apiErrorMessage(error, 'Product details are unavailable.'));
      }
    } finally {
      if (!controller.signal.aborted) setDetailLoading(false);
    }
  }

  const keys = [...new Set(state.rows.map(row => catalog ? row.product_id : `${row.product_id}:${row.version}`))];
  const visibleRows=state.rows.filter(row=>[row.product_id,row.name,row.domain,row.owner,row.version,row.status,row.lifecycle_state].some(value=>String(value || '').toLowerCase().includes(filter.toLowerCase())));
  return <section className="depo-panel data-cockpit" aria-label={title}>
    <div className="data-cockpit__intro"><div><span className="data-cockpit__eyebrow">Data lifecycle cockpit</span><h2>{title}</h2><p>{catalog ? 'Find data to reuse: discover ingested sources, identify owners and inspect published product versions.' : 'Turn source evidence into a governed, reusable package: inspect the analytics design, validate the contract and track catalog delivery.'}</p></div><IxButton onClick={load} disabled={state.loading}>Refresh</IxButton></div>
    <DataJourney current={catalog?'catalog':'products'}/>
    <div className="product-overview" aria-label="Workspace overview">
      <article><span>{catalog?'Catalog versions':'Retained package versions'}</span><strong>{state.loading||state.error?'—':state.total??'Unknown'}</strong><a href={catalog?'#/data-products':'#/catalog'}>{catalog?'Manage products and delivery':'Browse Data Catalog'}</a></article>
      <article><span>{catalog?'Registered ontologies (loaded)':'Imported schema drafts (loaded)'}</span><strong>{ontologyLoading||ontologyError||ontologyWarning?'—':catalog?(ontologies||[]).length:drafts.length}</strong><a href="#/import">Import source evidence</a></article>
      <article><span>{catalog?'Domains represented (loaded)':'Pending catalog delivery (loaded versions)'}</span><strong>{state.loading||state.error?'—':catalog?new Set(state.rows.map(row=>row.domain).filter(Boolean)).size:state.rows.filter(row=>row.status==='pending_catalog_registration').length}</strong>{catalog?<a href="#/data-products">Inspect package delivery</a>:<button type="button" className="product-overview__action" onClick={()=>setWorkspace('library')}>Inspect delivery status</button>}</article>
    </div>
    <p>Totals count product versions. Catalog entries and retained packages are separate records; pending delivery can make their totals differ.</p>
    {state.loading && <p role="status">Loading products…</p>}
    {state.error && <div role="alert" className="depo-alert depo-alert--warning">{state.error}</div>}
    {state.warning && <div role="alert" className="depo-alert depo-alert--warning">{state.warning}</div>}
    {(ontologyError||ontologyWarning)&&<p role="alert">Schema inventory: {ontologyError||ontologyWarning}</p>}
    <DataWorkspace label={catalog?'Catalog workspace':'Product workspace'} active={workspace} onChange={setWorkspace}
      tabs={catalog?[{id:'sources',label:'Ingested sources'},{id:'library',label:'Published products'},{id:'create',label:'Product opportunities'},{id:'governance',label:'Governance'}]:[{id:'library',label:'Product portfolio'},{id:'create',label:'Create & review'},{id:'governance',label:'Governance'}]}>
      {{sources:<IngestedDataInventory ontologies={ontologies || []}/>,library:<>
    <section aria-label="Discover product versions">
      <div className="product-discovery"><label>Find a product <input value={filter} onChange={event=>setFilter(event.target.value)} placeholder="Name, domain, owner, status or ID" /></label><span>{visibleRows.length} of {state.rows.length} loaded versions match</span></div>
      {!catalog&&state.rows.some(row=>row.status==='pending_catalog_registration')&&<p role="status">Some packages are retained but catalog delivery is pending. Select a package to inspect its delivery evidence.</p>}
      <p>Select a row to inspect ownership, readiness, source evidence and delivery.</p>
      <RegistryWidget title={`${title} (${state.total ?? '—'} total; ${state.rows.length} loaded)`} rows={visibleRows} columns={columns} height={320} showFilter={false} onRowClicked={row=>{if(row?.product_id)showDetail(catalog?row.product_id:`${row.product_id}:${row.version}`);}} />
      <label htmlFor="product-detail">Product details and versions</label>
      <select style={{padding:8,margin:8}} id="product-detail" value={selected} onChange={event=>showDetail(event.target.value)}>
        <option value="">Select a product</option>{keys.map(key=><option key={key} value={key}>{key}</option>)}
      </select>
      {detailLoading&&<p role="status">Loading product details…</p>}
      {detailError&&<div role="alert">{detailError}</div>}
      {detail&&<ProductEvidenceDetails detail={detail}/>}
    </section>
      {!state.loading&&!state.error&&!state.rows.length&&<div className="data-cockpit__empty"><h3>{catalog?'No published products yet':'Start with retained evidence'}</h3><p>{catalog?'Ingested sources remain discoverable in the Ingested sources tab. Published products appear here after approval and catalog delivery.':'Choose Create & review to build a product from a schema draft or completed pipeline run.'}</p><button type="button" className="depo-button" onClick={()=>setWorkspace(catalog?'sources':'create')}>{catalog?'Browse ingested sources':'Create a product'}</button></div>}
      </>,create:<>
      <div className="data-cockpit__guidance"><div><strong>Build from evidence, then review and publish</strong><p>Select structural analytics or pipeline evidence, inspect the retained source, then validate the publication contract.</p></div><a href="#/data-flow">Review Data Flow runs</a></div>
    <EvidenceProductOptions catalog={catalog} rows={state.rows} loading={state.loading} error={state.error}
      draftCount={ontologyLoading||ontologyError||ontologyWarning?null:drafts.length}
      onStructural={()=>revealEvidence('structural')} onPipeline={()=>revealEvidence('pipeline')}/>
    {!catalog && <details ref={pipelineRef} className="product-workspace-details" open={Boolean(runDraft)}><summary>Pipeline evidence: create a product from Data Flow</summary><section aria-label="Pipeline product evidence">
      <XmlAnalyticsLoader />
      <h3>Data Flow evidence</h3><p>Select a completed run in <a href="#/data-flow">Data Flow</a> to create a draft from its retained artifacts. Graph publication and product packaging are separate approved operations.</p>
      {runDraftError && <p role="alert">{runDraftError}</p>}
      {runDraft && <SchemaProductPublisher draft={runDraft} />}
    </section></details>}
    {!catalog && <details ref={structuralRef} className="product-workspace-details"><summary>Structural analytics: schema, dimensions and KPIs</summary><section aria-label="Schema design drafts">
      <h3>Schema design drafts ({drafts.length})</h3>
      {ontologyLoading && <p role="status">Loading ontology draft metadata…</p>}
      <p>Retained conversion evidence is a draft, not a published warehouse. Publication requires an approved semantic release and data-product steward approval.</p>
      <select aria-label="Schema design draft" value={draft ? selectedDraft : ''} onChange={event => setSelectedDraft(event.target.value)}>
        <option value="">Select imported schema draft</option>
        {drafts.map(ontology => <option key={ontology.ontology_id} value={ontology.ontology_id}>{ontology.label}</option>)}
      </select>
      <AnalyticsSchemaReview ontologyId={draft?.ontology_id} />
      {draft && <details><summary>Retained draft evidence</summary><pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 350, overflow: 'auto' }}>{JSON.stringify(draft.data_product_draft, null, 2)}</pre></details>}
      <SchemaProductPublisher draft={selectedProductDraft} />
      {!ontologyLoading && !ontologyError && !ontologyWarning && !drafts.length && <p>No retained schema-design draft metadata is available. Older imports may need reimporting with this release to retain their evidence references.</p>}
    </section></details>}
      </>,governance:<>
      <div className="data-cockpit__guidance"><div><strong>Review readiness before publication</strong><p>Confirm source provenance, ownership, quality evidence and an approved semantic release. Agent recommendations support the review; approval remains an explicit action.</p></div><a href="#/ontology">Review semantic releases</a></div>
    {!state.loading && !state.error && !state.warning && state.rows.length === 0 && <details className="product-workspace-details"><summary>How to publish your first governed product</summary><FirstProductGuide catalog={catalog} /></details>}
    <details className="product-workspace-details"><summary>Ask the product governor to review evidence</summary><AgentProposalPanel title="Product governance recommendations" agentIds={['data-product-governor']} context={{ page: catalog ? 'catalog' : 'data-products', product_ids: state.rows.map(row => row.product_id).slice(0, 20) }} /></details>
      </>}}
    </DataWorkspace>
  </section>;
}
import AgentProposalPanel from '../Components/AgentProposalPanel';
