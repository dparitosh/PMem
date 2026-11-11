import React, { lazy, Suspense, useState, useEffect, useCallback, useRef } from 'react';
import { IxBadge, IxButton, IxCard, IxCardContent, IxCardTitle, IxCol, IxLayoutGrid } from '@siemens/ix-react';
import { graphApi } from '../services/graphApi';
import ErrorBoundary from './ErrorBoundary';
import { UI_COLORS } from '../styles/uiTokens';
import './LandingPage.css';
import { useOntologies } from '../contexts/OntologyContext';
import { BRAND } from '../brand';
import EmbeddedFoundationEntry from './ontology/EmbeddedFoundationEntry';

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
      {!(metrics.existing_ontology?.resources > 0) && <p className="ix-landing-page__projection-note">Registry registration and graph publication are separate. Review the publication status in Models & Vocabularies; if it is published, refresh data and check the selected version.</p>}
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
    <p className="ix-landing-page__registry-help">{ontologies.length} registered {ontologies.length === 1 ? 'ontology' : 'ontologies'}. Open one to inspect its vocabulary and publication.</p>
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
          </dl><p>Registration does not establish graph publication or approval. Check the selected version in Models & Vocabularies.</p></details>
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
  const [selectedOntology, setSelectedOntology] = useState('');
  const [metrics, setMetrics] = useState(null);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const { ontologies, loading: ontologiesLoading, error: ontologiesError, warning: ontologiesWarning, fetchOntologies: loadOntologies } = useOntologies();
  const [metricsError, setMetricsError] = useState('');
  const [lastRefreshed, setLastRefreshed] = useState(null);
  const metricsRequest = useRef(null);
  const selectedRow = ontologies.find(o => (o.ontology_id || o.id) === selectedOntology);
  const selectedPrefix = selectedRow?.prefix || selectedRow?.ontology_prefix || '';

  useEffect(() => {
    if (!ontologiesLoading && !ontologiesError && selectedOntology && !selectedRow) {
      setSelectedOntology('');
    }
  }, [ontologiesLoading, ontologiesError, selectedOntology, selectedRow]);

  const loadMetrics = useCallback(async () => {
    metricsRequest.current?.abort();
    const controller = new AbortController(); metricsRequest.current = controller;
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
    const refresh = () => loadMetrics();
    window.addEventListener('depo:credentials-changed', refresh);
    window.addEventListener('depo:credentials-cleared', refresh);
    window.addEventListener('depo:ontologies-changed', refresh);
    window.addEventListener('focus', refresh);
    return () => {
      metricsRequest.current?.abort();
      window.removeEventListener('depo:credentials-changed', refresh);
      window.removeEventListener('depo:credentials-cleared', refresh);
      window.removeEventListener('depo:ontologies-changed', refresh);
      window.removeEventListener('focus', refresh);
    };
  }, [loadMetrics]);

  return (
    <div className="ix-landing-page">
      <section className="ix-landing-page__intro" aria-label="Platform overview">
        <div>
          <IxBadge type="label" variant="info" label="Digital thread workspace" />
          <h1>Engineering knowledge, connected. Decisions, grounded.</h1>
          <p>Govern ontology assets and trace product knowledge across PLM, MBSE and manufacturing.</p>
          <p className="ix-landing-page__foundation-brand"><strong>{BRAND.name}</strong> is grounded in PCA IDO and DIN EN 61360.</p>
          <nav aria-label="Start a task" className="ix-landing-page__tasks">
            <ul>
              <li><a href="#/import">Import engineering data</a><span>Load PLM, CAD and requirement sources.</span></li>
              <li><a href="#/graph">Explore the graph</a><span>Find parts, assemblies and their links.</span></li>
              <li><a href="#/recommendations">Assess a change</a><span>Review impact and reuse evidence before deciding.</span></li>
            </ul>
          </nav>
        </div>
        <div className="ix-landing-page__intro-actions">
          {lastRefreshed && <span>Updated {lastRefreshed.toLocaleTimeString()}</span>}
          <IxButton type="button" variant="secondary" icon="refresh" onClick={() => { loadMetrics(); loadOntologies(); }}>Refresh data</IxButton>
        </div>
      </section>

      <IxLayoutGrid className="ix-landing-page__workspace" columns={12} gap="16" noMargin>
        <IxCol size={4} sizeMd={12}>
          <div className="ix-landing-page__insights">
          <section className="ix-landing-page__card ix-landing-page__registry" aria-label="Ontology library">
            <h2>Ontology registry</h2>
              <details className="ix-landing-page__foundation-summary"><summary>Embedded foundation · ISO 23726-1 / IDO</summary><EmbeddedFoundationEntry /></details>
              <h3>Registered ontologies</h3>
              {ontologiesWarning && <div role="alert" className="ix-landing-page__alert">{ontologiesWarning}<IxButton type="button" variant="tertiary" onClick={() => loadOntologies(true)}>Retry registries</IxButton></div>}
              {ontologiesError ? <div role="alert" className="ix-landing-page__alert">{ontologiesError}<IxButton type="button" variant="tertiary" onClick={loadOntologies}>Retry</IxButton></div> : <OntologyList ontologies={ontologies} loading={ontologiesLoading} />}
          </section>
          <IxCard variant="outline" className="ix-landing-page__card ix-landing-page__profile">
            <IxCardTitle>Graph profile</IxCardTitle>
            <IxCardContent>
              <div className="ix-landing-page__profile-scroll" role="region" aria-label="Graph profile metrics" tabIndex={0}>
              <label className="ix-landing-page__scope">Ontology scope
                <select value={selectedOntology} onChange={event => setSelectedOntology(event.target.value)}>
                  <option value="">All ontologies</option>
                  {ontologies.map(o => { const id = o.ontology_id || o.id; return id ? <option key={id} value={id}>{o.label || o.ontology_name || o.name || id}</option> : null; })}
                </select>
              </label>
              {metricsError ? <div role="alert" className="ix-landing-page__alert">{metricsError}<IxButton type="button" variant="tertiary" onClick={loadMetrics}>Retry</IxButton></div> : metricsLoading && !metrics ? <div className="ix-landing-page__empty">Loading graph metrics…</div> : <>
                <GraphProfileMetrics metrics={metrics} />
              </>}
              </div>
            </IxCardContent>
          </IxCard>
          </div>
        </IxCol>
        <IxCol size={8} sizeMd={12}>
          <section className="ix-landing-page__chat" aria-label="Knowledge companion">
          <h2 className="ix-landing-page__chat-title">Knowledge companion</h2>
          <div className="ix-landing-page__chat-body">
            <ErrorBoundary>
              <Suspense fallback={<div className="depo-muted">Loading Knowledge Companion…</div>}>
                <Chatbot pageId="home" setChatResults={setChatResults} ontologyId={selectedOntology} ontologyPrefix={selectedPrefix} />
              </Suspense>
            </ErrorBoundary>
          </div>
          </section>
        </IxCol>
      </IxLayoutGrid>
    </div>
  );
}
