import React, { lazy, Suspense, useState, useEffect, useCallback, useRef } from 'react';
import { IxBadge, IxButton, IxCard, IxCardContent, IxCardTitle, IxCol, IxLayoutGrid } from '@siemens/ix-react';
import { graphApi } from '../services/graphApi';
import ErrorBoundary from './ErrorBoundary';
import { UI_COLORS } from '../styles/uiTokens';
import './LandingPage.css';
import { useOntologies } from '../contexts/OntologyContext';

const Chatbot = lazy(() => import('./Chatbot'));

// â”€â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function fmt(n) {
  if (n == null) return '-';
  return Number(n).toLocaleString();
}

export function ExistingOntologyMetrics({ metrics }) {
  return <section aria-label="Existing ontology metrics">
    <h3>Existing ontology records</h3>
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
      <p role="status" className="ix-landing-page__projection-note">RDF projection not published for this scope.</p>
      {!(metrics.existing_ontology?.resources > 0) && <p className="ix-landing-page__projection-note">No ontology graph records are available for this scope.</p>}
    </>;
  }
  return <>
                <div className="ix-landing-page__metric-row" aria-label="Published ontology metrics">
                  {[['classes', 'Declared classes'], ['object_properties', 'Object properties'], ['data_properties', 'Data properties'], ['annotation_properties', 'Annotation properties'], ['named_individuals', 'Declared named individuals'], ['resources', 'Graph resources'], ['relationships', 'Resource relationships']].map(([key, label]) =>
                    <div key={key}><strong>{fmt(metrics?.[key])}</strong><span>{label}</span></div>)}
                </div>
                <p className="ix-landing-page__projection-note">{metrics?.definition}</p>
                <p className="ix-landing-page__projection-note">Complete counts for the published projection; inferred axioms and unpublished registry artifacts are excluded.</p>


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

export function OntologyList({ ontologies, loading }) {
  if (loading) return <div style={{ color: UI_COLORS.textSec, fontSize: 12, padding: 8 }}>Loading ontologies...</div>;
  if (!ontologies.length) return <div style={{ color: UI_COLORS.textSec, fontSize: 12, padding: 8 }}>No ontologies registered yet.</div>;

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: 'var(--theme-color-component-2)', color: 'var(--theme-color-std-text)', borderBottom: '1px solid #cfd8e3' }}>
            {['Name', 'Prefix', 'Type', 'Uses', 'Last used / registered'].map(h => (
              <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 600 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ontologies.map((o, i) => (
            <tr key={o.id || i} style={{ background: i % 2 === 0 ? 'var(--theme-color-component-1)' : 'transparent' }}>
              <td style={{ padding: '6px 10px', fontWeight: 600, color: 'var(--ui-primary, #005a9c)' }}>
                {o.label || o.name || o.ontology_name || o.prefix || o.id || o.ontology_id}
              </td>
              <td style={{ padding: '6px 10px' }}>{o.prefix || o.ontology_prefix || 'Not supplied'}</td>
              <td style={{ padding: '6px 10px' }}>
                <span style={{
                  background: UI_COLORS.primaryLight, color: 'var(--ui-primary, #005a9c)',
                  borderRadius: 4, padding: '2px 7px', fontSize: 11, fontWeight: 600,
                }}>
                  {ontologyTypeLabel(o).toUpperCase()}
                </span>
              </td>
              <td style={{ padding: '6px 10px', color: 'var(--theme-color-std-text)' }}>{fmt(o.usageCount)}</td>
              <td style={{ padding: '6px 10px', color: 'var(--theme-color-soft-text)' }}>
                {o.lastUsed || o.created_at ? new Date(o.lastUsed || o.created_at).toLocaleDateString() : '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// â”€â”€â”€ Metrics breakdown tables â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
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

// â”€â”€â”€ Main landing page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    const refresh = () => loadMetrics();
    window.addEventListener('depo:credentials-changed', refresh);
    window.addEventListener('depo:credentials-cleared', refresh);
    window.addEventListener('depo:ontologies-changed', refresh);
    return () => {
      metricsRequest.current?.abort();
      window.removeEventListener('depo:credentials-changed', refresh);
      window.removeEventListener('depo:credentials-cleared', refresh);
      window.removeEventListener('depo:ontologies-changed', refresh);
    };
  }, [loadMetrics]);

  return (
    <div className="ix-landing-page">
      <section className="ix-landing-page__intro" aria-label="Platform overview">
        <div>
          <IxBadge type="label" variant="info" label="Digital thread workspace" />
          <h2>Knowledge at the point of engineering work</h2>
          <p>Govern ontology assets and expose traceable product knowledge across PLM, MBSE, and manufacturing.</p>
        </div>
        <div className="ix-landing-page__intro-actions">
          {lastRefreshed && <span>Updated {lastRefreshed.toLocaleTimeString()}</span>}
          <IxButton type="button" variant="secondary" icon="refresh" onClick={() => { loadMetrics(); loadOntologies(); }}>Refresh data</IxButton>
        </div>
      </section>

      <IxLayoutGrid className="ix-landing-page__workspace" columns={12} gap="16" noMargin>
        <IxCol size={4} sizeMd={12}>
          <div className="ix-landing-page__insights">
          <IxCard variant="outline" className="ix-landing-page__card ix-landing-page__registry">
            <IxCardTitle>Ontology registry</IxCardTitle>
            <IxCardContent>
              {ontologiesWarning && <div role="alert" className="ix-landing-page__alert">{ontologiesWarning}<IxButton type="button" variant="tertiary" onClick={() => loadOntologies(true)}>Retry registries</IxButton></div>}
              {ontologiesError ? <div role="alert" className="ix-landing-page__alert">{ontologiesError}<IxButton type="button" variant="tertiary" onClick={loadOntologies}>Retry</IxButton></div> : <OntologyList ontologies={ontologies} loading={ontologiesLoading} />}
            </IxCardContent>
          </IxCard>
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
              {metricsError ? <div role="alert" className="ix-landing-page__alert">{metricsError}<IxButton type="button" variant="tertiary" onClick={loadMetrics}>Retry</IxButton></div> : metricsLoading ? <div className="ix-landing-page__empty">Loading graph metrics…</div> : <>
                <GraphProfileMetrics metrics={metrics} />
              </>}
              </div>
            </IxCardContent>
          </IxCard>
          </div>
        </IxCol>
        <IxCol size={8} sizeMd={12}>
          <section className="ix-landing-page__chat" aria-label="Knowledge companion">
          <h3 className="ix-landing-page__chat-title">Knowledge companion</h3>
          <div className="ix-landing-page__chat-body">
            <ErrorBoundary>
              <Suspense fallback={<div className="depo-muted">Loading Knowledge Companion…</div>}>
                <Chatbot setChatResults={setChatResults} ontologyId={selectedOntology} ontologyPrefix={selectedPrefix} />
              </Suspense>
            </ErrorBoundary>
          </div>
          </section>
        </IxCol>
      </IxLayoutGrid>
    </div>
  );
}
