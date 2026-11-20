import React, { lazy, Suspense, useState, useEffect, useCallback, useRef } from 'react';
import { graphApi } from '../services/graphApi';
import ErrorBoundary from './ErrorBoundary';
import './LandingPage.css';
import { useOntologies } from '../contexts/OntologyContext';
import { BRAND } from '../brand';
import { UI_COLORS } from '../styles/uiTokens';
import HomeKnowledgeOverview from './HomeKnowledgeOverview';

const Chatbot = lazy(() => import('./Chatbot'));

// ─── helpers ─────────────────────────────────────────────────────────────────
function fmt(n) {
  if (n == null) return '-';
  return Number(n).toLocaleString();
}

export function ExistingOntologyMetrics({ metrics }) {
  return <section aria-label="Existing ontology metrics">
    <h2>Existing ontology records</h2>
    <p className="ix-landing-page__projection-note">{metrics.definition} Chat searches these records as well as published RDF resources.</p>
    <div className="ix-landing-page__metric-row">
      {[['classes', 'Class records'], ['object_properties', 'Object property records'], ['data_properties', 'Data property records'], ['annotation_properties', 'Annotation property records'], ['named_individuals', 'Named individual records'], ['resources', 'Total existing records'], ['relationships', 'Existing record relationships']].map(([key, label]) =>
        <div key={key}><strong>{fmt(metrics[key])}</strong><span>{label}</span></div>)}
    </div>
  </section>;
}

export function GraphProfileMetrics({ metrics }) {
  if (metrics?.resources === 0) {
    return <>
      {metrics.existing_ontology?.resources > 0 && <ExistingOntologyMetrics metrics={metrics.existing_ontology} />}
      <p role="status" className="ix-landing-page__projection-note">No published RDF resources were found for this scope.</p>
      {!(metrics.existing_ontology?.resources > 0) && <p className="ix-landing-page__projection-note">Registry registration and graph publication are separate. Review the publication status in Ontology & Vocabularies; if it is published, refresh data and check the selected version.</p>}
    </>;
  }
  return <>
                <div className="ix-landing-page__metric-row" aria-label="Published ontology metrics">
                  {[['classes', 'Declared classes'], ['object_properties', 'Object properties'], ['data_properties', 'Data properties'], ['annotation_properties', 'Declared annotation properties'], ['named_individuals', 'Declared named individuals'], ['business_instances', 'Business instance records'], ['resources', 'Graph resources'], ['relationships', 'Resource relationships']].map(([key, label]) =>
                    <div key={key}><strong>{fmt(metrics?.[key])}</strong><span>{label}</span></div>)}
                </div>
                <p className="ix-landing-page__projection-note">Zero annotation-property declarations does not mean labels or descriptions are missing. Business instances can have a domain class without an explicit named-individual declaration.</p>
                <details className="ix-landing-page__projection-note"><summary>How these counts are defined</summary>
                  <p>{metrics?.definition}</p>
                  <p>Complete counts for the published projection; inferred axioms and unpublished registry artifacts are excluded.</p>
                </details>


                <BreakdownTable title="Graph resources by ontology" rows={metrics?.ontology_breakdown || []} colKey="ontology" colLabel="Resources" />
                {metrics?.breakdown_truncated && <p className="ix-landing-page__projection-note">Showing the largest 200 ontologies; aggregate totals include all ontologies.</p>}

    {metrics?.existing_ontology?.resources > 0 && <ExistingOntologyMetrics metrics={metrics.existing_ontology} />}
  </>;
}

export function ontologyTypeLabel(ontology) {
  const type = [ontology.ontology_type, ontology.schema_format, ontology.file_type, ontology.type]
    .find(value => value && !['neo4j', 'neo4j_live', 'neo4j_projection'].includes(String(value).toLowerCase()));
  if (type) return type;
  if (ontology.source === 'engineering-conversion:express') return 'EXPRESS schema';
  if (ontology.source === 'legacy_ingestion_migration') return 'Ontology';
  return 'Ontology';
}

const REGISTRY_PREVIEW = 8;

export function OntologyList({ ontologies = [], loading }) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? ontologies : ontologies.slice(0, REGISTRY_PREVIEW);
  if (loading && !ontologies.length) return <p role="status">Loading ontologies…</p>;
  if (!ontologies.length) return <p>No ontologies registered yet. <a href="#/import">Import an ontology</a></p>;
  return <section className="ix-landing-page__ontology-list" aria-label="Ontology registry">
    <p className="ix-landing-page__registry-help">{ontologies.length} registered {ontologies.length === 1 ? 'ontology' : 'ontologies'}.</p>
    {loading && <p role="status">Refreshing registry…</p>}
    <ul aria-label="Registered ontologies">
      {visible.map((o, i) => {
        const id = o.ontology_id || o.id || o.value;
        const label = o.label || o.name || o.ontology_name || o.prefix || id || 'Unnamed ontology';
        const prefix = o.prefix || o.ontology_prefix;
        const date = o.created_at ? new Date(o.created_at) : null;
        const validDate = date && !Number.isNaN(date.getTime());
        const merged = String(o.source || '').startsWith('governed-merge:') || o.status === 'merged';
        return <li key={id || i}>
          <div className="ix-landing-page__ontology-name" title={label}>{id ? <a href={`#/ontology?target=${encodeURIComponent(id)}`}>{label}</a> : <strong>{label}</strong>}</div>
          <div className="ix-landing-page__ontology-meta"><span>{merged ? 'Merged vocabulary' : 'Registered vocabulary'}</span>{prefix && <span>Prefix: {prefix}</span>}</div>
          <details><summary>Registration details</summary><dl>
            <dt>Prefix</dt><dd>{prefix || 'Not supplied'}</dd>
            <dt>Format</dt><dd>{ontologyTypeLabel(o)}</dd>
            <dt>Source version</dt><dd>{o.version || o.ontology_version || 'Not supplied'}</dd>
            <dt>Registered</dt><dd>{validDate ? date.toLocaleDateString() : 'Not supplied'}</dd>
            <dt>Identity</dt><dd>{id || 'Not supplied'}</dd>
          </dl><p>Registration does not establish graph publication or approval. Check the selected version in Ontology & Vocabularies.</p></details>
        </li>;
      })}
    </ul>
    {ontologies.length > REGISTRY_PREVIEW && <button type="button" className="ix-landing-page__registry-toggle" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? 'Show fewer' : `Show all ${ontologies.length} ontologies`}</button>}
  </section>;
}

// ─── Metrics breakdown tables ─────────────────────────────────────────────────
function BreakdownTable({ title, rows, colKey, colLabel = 'Count' }) {
  if (!rows || !rows.length) {
    return (
      <div className="ix-landing-page__empty-state">
        <strong>{title}</strong>
        <span>No published graph data is available yet.</span>
      </div>
    );
  }
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--theme-color-std-text)', marginBottom: 4 }}>{title}</div>
      <div style={{ overflowX: 'auto', maxHeight: 160, overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
          <thead>
            <tr style={{ background: 'var(--theme-color-component-2)' }}>
              <th style={{ padding: '4px 8px', textAlign: 'left', color: 'var(--theme-color-std-text)' }}>Name</th>
              <th style={{ padding: '4px 8px', textAlign: 'right', color: 'var(--theme-color-std-text)' }}>{colLabel}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const maxCount = Math.max(1, ...rows.map(row => Number(row.count ?? row.node_count) || 0));
              const cnt = r.count ?? r.node_count ?? 0;
              const pct = Math.round((cnt / maxCount) * 100);
              return (
                <tr key={i} style={{ background: i % 2 === 0 ? 'transparent' : 'var(--theme-color-component-1)' }}>
                  <td style={{ padding: '4px 8px', color: 'var(--ui-primary, #005a9c)', fontWeight: 500 }}>
                    {r[colKey] || '-'}
                  </td>
                  <td style={{ padding: '4px 8px', textAlign: 'right' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                      <div style={{
                        width: 60, height: 6, background: '#e8edf3',
                        borderRadius: 3, overflow: 'hidden',
                      }}>
                        <div style={{
                          width: `${pct}%`, height: '100%',
                          background: UI_COLORS.primary, borderRadius: 3,
                        }} />
                      </div>
                      <span style={{ color: 'var(--theme-color-std-text)', minWidth: 36, textAlign: 'right' }}>{fmt(cnt)}</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Main landing page ────────────────────────────────────────────────────────
const responsePayload = (response) => {
  const value = response?.data ?? response ?? {};
  return value?.data && typeof value.data === 'object' && !Array.isArray(value.data) ? value.data : value;
};

export default function LandingPage({ setChatResults, onNavigate }) {
  const readScope=()=>new URLSearchParams(window.location.hash.split('?')[1]||'').get('ontology_id')||'';
  const [selectedOntology, setSelectedOntology] = useState(readScope);
  const [refreshRevision,setRefreshRevision]=useState(0);
  const [selectedNode,setSelectedNode]=useState(null);
  const selectScope=useCallback(value=>{const params=new URLSearchParams(window.location.hash.split('?')[1]||'');if(value)params.set('ontology_id',value);else params.delete('ontology_id');const query=params.toString();window.history.pushState(null,'',`#/home${query?'?'+query:''}`);setSelectedOntology(value);setSelectedNode(null);},[]);
  useEffect(()=>{const restore=()=>{setSelectedOntology(readScope());setSelectedNode(null);};window.addEventListener('hashchange',restore);window.addEventListener('popstate',restore);return()=>{window.removeEventListener('hashchange',restore);window.removeEventListener('popstate',restore);};},[]);
  const [metrics, setMetrics] = useState(null);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const { ontologies, loading: ontologiesLoading, error: ontologiesError, fetchOntologies: loadOntologies } = useOntologies();
  const [metricsError, setMetricsError] = useState('');
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const metricsRequest = useRef(null);
  const selectedRow = ontologies.find(o => (o.ontology_id || o.id) === selectedOntology);
  const selectedPrefix = selectedRow?.prefix || selectedRow?.ontology_prefix || '';

  useEffect(() => {
    if (!ontologiesLoading && !ontologiesError && selectedOntology && !selectedRow) {
      selectScope('');
    }
  }, [ontologiesLoading, ontologiesError, selectedOntology, selectedRow,selectScope]);

  const loadMetrics = useCallback(async () => {
    metricsRequest.current?.abort();
    const controller = new AbortController(); metricsRequest.current = controller;
    setMetrics(null);
    setMetricsLoading(true);
    setMetricsError('');
    try {
      const response = await graphApi.getMetrics(selectedOntology, controller.signal, selectedPrefix);
      if (controller.signal.aborted) return;
      const graph = responsePayload(response);
      if (graph.scope?.sampled !== false || graph.scope?.type !== 'published_rdf_projection' ||
          (graph.scope?.ontology_id || '') !== selectedOntology) throw new Error('Graph service returned an incompatible metrics scope. Deploy matching frontend and graph service files.');
      setMetrics(graph);
      setLastRefreshed(new Date());
    } catch (error) {
      if (controller.signal.aborted) return;
      const detail = error?.response?.data?.detail;
      setMetricsError(error?.response?.status === 401 || error?.response?.status === 403
        ? 'Graph access is required. Open Admin → Service credentials and connect registered services, then retry.'
        : error?.response?.status === 404 ? 'Graph metrics route is missing. Update the graph service and import its updated OpenAPI contract into the gateway, if used.'
        : (typeof detail === 'string' ? detail : error.message || 'Graph metrics are currently unavailable.'));
      setMetrics(null);
    } finally {
      if (!controller.signal.aborted) setMetricsLoading(false);
    }
  }, [selectedOntology, selectedPrefix]);

  useEffect(() => {
    loadMetrics();
    const refresh = () => {loadMetrics();setRefreshRevision(value=>value+1);};
    const reset=()=>{setMetrics(null);setSelectedNode(null);setLastRefreshed(null);loadMetrics();};
    const sessionEvents=['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired'];
    sessionEvents.forEach(name=>window.addEventListener(name,reset));

    window.addEventListener('depo:ontologies-changed', refresh);
    window.addEventListener('focus', refresh);
    return () => {
      metricsRequest.current?.abort();
      sessionEvents.forEach(name=>window.removeEventListener(name,reset));
      window.removeEventListener('depo:ontologies-changed', refresh);
      window.removeEventListener('focus', refresh);
    };
  }, [loadMetrics]);

  return <div className="ix-landing-page home-workspace">
    <section className="home-welcome" aria-label="Platform overview">
      <div className="home-welcome-heading"><div><h1>Explore engineering knowledge and make informed decisions.</h1></div><button type="button" className="home-refresh" onClick={()=>{loadMetrics();loadOntologies();setRefreshRevision(value=>value+1);}}>Refresh data</button></div>
      <section className="home-question" aria-label="Knowledge companion"><ErrorBoundary><Suspense fallback={<p role="status">Loading Knowledge Companion…</p>}><Chatbot presentation="landing" pageId="home" setChatResults={setChatResults} ontologyId={selectedNode?.properties?.ontology_id||selectedNode?.properties?.source_ontology||selectedOntology} ontologyPrefix={selectedNode?.properties?.ontology_prefix||selectedNode?.properties?.prefix||selectedPrefix} nodeId={selectedNode?.elementId||''} contextLabel={selectedNode?.name||selectedNode?.properties?.name||selectedNode?.label||''}/></Suspense></ErrorBoundary></section>
    </section>
    <nav aria-label="Start a task" className="home-task-cards">
      <a href="#/ontology"><span className="home-task-icon" aria-hidden="true">◇</span><h2>Manage ontologies</h2><p>Vocabulary and validation</p><strong>Open Ontology Junction →</strong></a>
      <a href="#/import"><span className="home-task-icon" aria-hidden="true">↥</span><h2>Bring in engineering records</h2><p>PLM, CAD, requirements and manufacturing</p><strong>Import and link data →</strong></a>
      <a href={selectedNode?`#/recommendations?service=change-impact&node_id=${encodeURIComponent(selectedNode.elementId)}&name=${encodeURIComponent(selectedNode.name||selectedNode.properties?.name||selectedNode.label||'')}&ontology_id=${encodeURIComponent(selectedNode.properties?.ontology_id||selectedOntology)}&ontology_prefix=${encodeURIComponent(selectedNode.properties?.ontology_prefix||selectedPrefix)}`:'#/recommendations'}><span className="home-task-icon" aria-hidden="true">✓</span><h2>Review a decision</h2><p>Change impact, similar parts and dependencies</p><strong>Open Decision intelligence →</strong></a>
    </nav>
    <HomeKnowledgeOverview ontologyId={selectedOntology} revision={refreshRevision} onSelectNode={setSelectedNode}/>
    <section aria-labelledby="home-attention-title"><h2 id="home-attention-title">Your knowledge at a glance</h2><div className="home-attention-cards">
      <a href="#/ontology"><strong>{ontologiesError?'Unavailable':ontologiesLoading&&!ontologies.length?'…':ontologies.length}</strong><span>Registered ontologies</span><small>Review vocabulary and publication</small></a>
      <a href={selectedOntology?`#/graph?ontology_id=${encodeURIComponent(selectedOntology)}`:'#/graph'}><strong>{metricsError?'Unavailable':metricsLoading&&!metrics?'…':fmt(metrics?.business_instances)}</strong><span>Business instance records</span><small>Published scope · not a count of distinct physical parts</small></a>
      <a href="#/change-control"><strong>Review</strong><span>Changes and approvals</span><small>Inspect retained proposals and delivery</small></a>
      <a href="#/reports?view=memory"><strong>Recall</strong><span>Conversation and context</span><small>Find your retained questions and evidence</small></a>
    </div></section>
    <div className="home-reference-grid">
      <section className="home-panel home-profile" aria-label="Graph profile"><div className="home-panel-heading"><h2>Graph profile</h2>{lastRefreshed&&<small>Updated {lastRefreshed.toLocaleTimeString()}</small>}</div><div role="region" aria-label="Graph profile metrics" tabIndex={0}>
        <label className="ix-landing-page__scope">Ontology scope<select value={selectedOntology} onChange={event=>selectScope(event.target.value)}><option value="">All ontologies</option>{ontologies.map(o=>{const id=o.ontology_id||o.id;return id?<option key={id} value={id}>{o.label||o.ontology_name||o.name||id}</option>:null;})}</select></label>
        {metricsError?<p role="alert">{metricsError}<button type="button" onClick={loadMetrics}>Retry graph metrics</button></p>:metricsLoading&&!metrics?<p role="status">Loading graph metrics…</p>:<GraphProfileMetrics metrics={metrics}/>}
      </div></section>
    </div>
    <p className="home-foundation-note">{BRAND.name} · PCA IDO / ISO 23726-1 · DIN EN 61360</p>
  </div>;
}
