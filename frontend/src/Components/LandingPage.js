import React, { useState, useEffect, useCallback } from 'react';
import { healthAPI } from '../services/apiClient';
import Chatbot from './Chatbot';
import ErrorBoundary from './ErrorBoundary';

const DASHBOARD_ENABLED = true;

// ─── helpers ─────────────────────────────────────────────────────────────────
function fmt(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString();
}

function SectionTitle({ children }) {
  return (
    <div style={{
      fontSize: 13, fontWeight: 700, color: '#004B87',
      borderBottom: '2px solid #004B87', paddingBottom: 4, marginBottom: 10,
      textTransform: 'uppercase', letterSpacing: '0.05em',
    }}>
      {children}
    </div>
  );
}

// ─── Ontology list ────────────────────────────────────────────────────────────
function OntologyList({ ontologies, loading }) {
  if (loading) return <div style={{ color: '#888', fontSize: 12, padding: 8 }}>Loading ontologies…</div>;
  if (!ontologies.length) return <div style={{ color: '#888', fontSize: 12, padding: 8 }}>No ontologies registered yet.</div>;

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: '#004B87', color: '#fff' }}>
            {['Name', 'Type', 'Uses', 'Last Used'].map(h => (
              <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 600 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ontologies.map((o, i) => (
            <tr key={o.id || i} style={{ background: i % 2 === 0 ? '#f8f9fa' : '#fff' }}>
              <td style={{ padding: '6px 10px', fontWeight: 600, color: '#004B87' }}>{o.name || o.id}</td>
              <td style={{ padding: '6px 10px' }}>
                <span style={{
                  background: '#e8f0fe', color: '#004B87',
                  borderRadius: 4, padding: '2px 7px', fontSize: 11, fontWeight: 600,
                }}>
                  {(o.type || 'ontology').toUpperCase()}
                </span>
              </td>
              <td style={{ padding: '6px 10px', color: '#444' }}>{fmt(o.usageCount)}</td>
              <td style={{ padding: '6px 10px', color: '#777' }}>
                {o.lastUsed ? new Date(o.lastUsed).toLocaleDateString() : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Metrics breakdown tables ─────────────────────────────────────────────────
function BreakdownTable({ title, rows, colKey, colLabel = 'Count' }) {
  if (!rows || !rows.length) return null;
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontSize: 12, fontWeight: 700, color: '#333', marginBottom: 4 }}>{title}</div>
      <div style={{ overflowX: 'auto', maxHeight: 160, overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
          <thead>
            <tr style={{ background: '#f0f2f5' }}>
              <th style={{ padding: '4px 8px', textAlign: 'left', color: '#333' }}>Name</th>
              <th style={{ padding: '4px 8px', textAlign: 'right', color: '#333' }}>{colLabel}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const maxCount = (rows[0]?.count ?? rows[0]?.node_count) || 1;
              const cnt = r.count ?? r.node_count ?? 0;
              const pct = Math.round((cnt / maxCount) * 100);
              return (
                <tr key={i} style={{ background: i % 2 === 0 ? '#fff' : '#f8f9fa' }}>
                  <td style={{ padding: '4px 8px', color: '#004B87', fontWeight: 500 }}>
                    {r[colKey] || '—'}
                  </td>
                  <td style={{ padding: '4px 8px', textAlign: 'right' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, justifyContent: 'flex-end' }}>
                      <div style={{
                        width: 60, height: 6, background: '#e8edf3',
                        borderRadius: 3, overflow: 'hidden',
                      }}>
                        <div style={{
                          width: `${pct}%`, height: '100%',
                          background: '#004B87', borderRadius: 3,
                        }} />
                      </div>
                      <span style={{ color: '#333', minWidth: 36, textAlign: 'right' }}>{fmt(cnt)}</span>
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
export default function LandingPage({ setChatResults, onNavigate }) {
  const [metrics, setMetrics] = useState(null);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const [ontologies, setOntologies] = useState([]);
  const [ontologiesLoading, setOntologiesLoading] = useState(true);
  const [lastRefreshed, setLastRefreshed] = useState(null);

  const loadMetrics = useCallback(async () => {
    setMetricsLoading(true);
    try {
      const response = await healthAPI.graphMetrics();
      setMetrics(response.data);
      setLastRefreshed(new Date());
    } catch (error) {
      console.error('Failed to load metrics:', error);
      setMetrics({
        total_nodes: 0,
        total_relationships: 0,
        node_labels: [],
        relationship_types: [],
        ontology_breakdown: [],
        ontology_kpis: {},
      });
    } finally {
      setMetricsLoading(false);
    }
  }, []);

  const loadOntologies = useCallback(async () => {
    setOntologiesLoading(true);
    try {
      const response = await healthAPI.ontologiesAvailable();
      setOntologies(response.data.ontologies || []);
    } catch (error) {
      console.error('Failed to load ontologies:', error);
      setOntologies([]);
    } finally {
      setOntologiesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!DASHBOARD_ENABLED) return;
    loadMetrics();
    loadOntologies();
  }, [loadMetrics, loadOntologies]);

  if (!DASHBOARD_ENABLED) {
    return (
      <div style={{
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f4f6fa',
        padding: 24,
      }}>
        <div style={{
          width: 'min(640px, 100%)',
          background: '#fff',
          border: '1px solid #e2e6ea',
          borderRadius: 12,
          padding: 24,
          boxShadow: '0 8px 24px rgba(0, 75, 135, 0.08)',
        }}>
          <div style={{ fontSize: 22, fontWeight: 800, color: '#004B87', marginBottom: 8 }}>
            Dashboard Temporarily Disabled
          </div>
          <div style={{ fontSize: 14, color: '#445', lineHeight: 1.6 }}>
            The executive dashboard is currently turned off for maintenance.
            Core import and ontology operations remain available.
          </div>
          {typeof onNavigate === 'function' && (
            <div style={{ marginTop: 16 }}>
              <button
                onClick={() => onNavigate('data-import')}
                style={{
                  background: '#004B87',
                  color: '#fff',
                  border: 'none',
                  borderRadius: 6,
                  padding: '8px 14px',
                  fontSize: 13,
                  cursor: 'pointer',
                }}
              >
                Go to Data Import
              </button>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      background: '#f4f6fa', overflow: 'hidden',
    }}>
      {/* ── Top hero bar ───────────────────────────────────────────── */}
      <div style={{
        background: 'linear-gradient(135deg, #004B87 0%, #1a6fb5 100%)',
        color: '#fff', padding: '12px 20px',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, letterSpacing: '-0.02em' }}>
            Digital Engineering Ontology Hub
          </div>
          <div style={{ fontSize: 11, color: '#b8d4f0', marginTop: 2 }}>
            Knowledge graph · Digital thread · Traceability · Recommendations
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {lastRefreshed && (
            <span style={{ fontSize: 10, color: '#b8d4f0' }}>
              Updated {lastRefreshed.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={() => { loadMetrics(); loadOntologies(); }}
            style={{
              background: 'rgba(255,255,255,0.15)', color: '#fff',
              border: '1px solid rgba(255,255,255,0.3)',
              borderRadius: 6, padding: '4px 12px', fontSize: 12, cursor: 'pointer',
            }}
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* ── Main body: left panel (metrics + ontologies) + right (chat) ─ */}
      <div style={{ flex: '1 1 0', minHeight: 0, display: 'flex', gap: 0, overflow: 'hidden' }}>

        {/* Left panel */}
        <div style={{
          width: 380, minWidth: 300, maxWidth: 460, flexShrink: 0,
          display: 'flex', flexDirection: 'column', gap: 0,
          borderRight: '1px solid #e2e6ea', background: '#fff', overflow: 'hidden',
        }}>

          {/* Ontology list */}
          <div style={{ flexShrink: 0, padding: '12px 14px', borderBottom: '1px solid #e8edf3' }}>
            <SectionTitle>Ontologies</SectionTitle>
            <OntologyList ontologies={ontologies} loading={ontologiesLoading} />
          </div>

          {/* Ontology breakdown */}
          <div style={{ flex: '1 1 0', minHeight: 0, overflowY: 'auto', padding: '12px 14px' }}>
            <SectionTitle>Graph Metrics</SectionTitle>

            {metricsLoading ? (
              <div style={{ color: '#888', fontSize: 12 }}>Loading metrics…</div>
            ) : (
              <>
                {metrics?.ontology_breakdown?.length > 0 && (
                  <BreakdownTable
                    title="Nodes by Ontology / Source"
                    rows={metrics.ontology_breakdown}
                    colKey="ontology"
                    colLabel="Nodes"
                  />
                )}
                <BreakdownTable
                  title="Top Node Labels"
                  rows={metrics?.node_labels || []}
                  colKey="label"
                  colLabel="Count"
                />
                <BreakdownTable
                  title="Top Relationship Types"
                  rows={metrics?.relationship_types || []}
                  colKey="type"
                  colLabel="Count"
                />

                <div style={{ marginTop: 10 }}>
                  <div style={{ fontSize: 12, fontWeight: 700, color: '#333', marginBottom: 4 }}>
                    Protege-style Ontology KPIs
                  </div>
                  <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
                      <thead>
                        <tr style={{ background: '#f0f2f5' }}>
                          <th style={{ padding: '4px 8px', textAlign: 'left', color: '#333' }}>Metric</th>
                          <th style={{ padding: '4px 8px', textAlign: 'right', color: '#333' }}>Value</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          ['Classes', metrics?.ontology_kpis?.classes],
                          ['Axiom Proxy Count', metrics?.ontology_kpis?.axiom_proxy_count],
                          ['Class/Property Ratio', metrics?.ontology_kpis?.class_to_property_ratio],
                        ].map(([k, v], i) => (
                          <tr key={k} style={{ background: i % 2 === 0 ? '#fff' : '#f8f9fa' }}>
                            <td style={{ padding: '4px 8px', color: '#004B87', fontWeight: 500 }}>{k}</td>
                            <td style={{ padding: '4px 8px', textAlign: 'right', color: '#333' }}>{fmt(v)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

              </>
            )}
          </div>
        </div>

        {/* Chat panel */}
        <div style={{ flex: '1 1 0', minHeight: 0, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          <ErrorBoundary>
            <Chatbot setChatResults={setChatResults} />
          </ErrorBoundary>
        </div>
      </div>
    </div>
  );
}
