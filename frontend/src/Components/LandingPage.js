import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw } from 'lucide-react';
import { healthAPI } from '../services/apiClient';
import Chatbot from './Chatbot';
import ErrorBoundary from './ErrorBoundary';
import logger from '../utils/logger';
import { UI_COLORS } from '../styles/uiTokens';

const DASHBOARD_ENABLED = true;

// â”€â”€â”€ helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function fmt(n) {
  if (n == null) return '-';
  return Number(n).toLocaleString();
}

function SectionTitle({ children }) {
  return (
    <div style={{
      fontSize: 10,
      fontWeight: 800,
      color: UI_COLORS.primary,
      paddingBottom: 4,
      marginBottom: 10,
      textTransform: 'uppercase',
      letterSpacing: '0.1em',
    }}>
      {children}
    </div>
  );
}

// â”€â”€â”€ Ontology list â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
function OntologyList({ ontologies, loading }) {
  if (loading) return <div style={{ color: '#888', fontSize: 12, padding: 8 }}>Loading ontologies...</div>;
  if (!ontologies.length) return <div style={{ color: '#888', fontSize: 12, padding: 8 }}>No ontologies registered yet.</div>;

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: UI_COLORS.primary, color: '#fff' }}>
            {['Name', 'Type', 'Uses', 'Last Used'].map(h => (
              <th key={h} style={{ padding: '6px 10px', textAlign: 'left', fontWeight: 600 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ontologies.map((o, i) => (
            <tr key={o.id || i} style={{ background: i % 2 === 0 ? '#f8f9fa' : '#fff' }}>
              <td style={{ padding: '6px 10px', fontWeight: 600, color: UI_COLORS.primary }}>{o.name || o.id}</td>
              <td style={{ padding: '6px 10px' }}>
                <span style={{
                  background: UI_COLORS.primaryLight, color: UI_COLORS.primary,
                  borderRadius: 4, padding: '2px 7px', fontSize: 11, fontWeight: 600,
                }}>
                  {(o.type || 'ontology').toUpperCase()}
                </span>
              </td>
              <td style={{ padding: '6px 10px', color: '#444' }}>{fmt(o.usageCount)}</td>
              <td style={{ padding: '6px 10px', color: '#777' }}>
                {o.lastUsed ? new Date(o.lastUsed).toLocaleDateString() : '-'}
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
                  <td style={{ padding: '4px 8px', color: UI_COLORS.primary, fontWeight: 500 }}>
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

// â”€â”€â”€ Main landing page â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
export default function LandingPage({ setChatResults, onNavigate }) {
  const [metrics, setMetrics] = useState(null);
  const [metricsLoading, setMetricsLoading] = useState(true);
  const [ontologies, setOntologies] = useState([]);
  const [ontologiesLoading, setOntologiesLoading] = useState(true);
  const [metricsError, setMetricsError] = useState('');
  const [ontologiesError, setOntologiesError] = useState('');
  const [lastRefreshed, setLastRefreshed] = useState(null);

  const loadMetrics = useCallback(async () => {
    setMetricsLoading(true);
    setMetricsError('');
    try {
      const response = await healthAPI.graphMetrics();
      setMetrics(response?.data ?? {
        total_nodes: 0,
        total_relationships: 0,
        node_labels: [],
        relationship_types: [],
        ontology_breakdown: [],
        ontology_kpis: {},
      });
      setLastRefreshed(new Date());
    } catch (error) {
      logger.error('Failed to load metrics:', error);
      setMetricsError('Graph metrics are currently unavailable.');
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
    setOntologiesError('');
    try {
      const response = await healthAPI.ontologiesAvailable();
      setOntologies(response?.data?.ontologies || []);
    } catch (error) {
      logger.error('Failed to load ontologies:', error);
      setOntologiesError('Ontology registry is currently unavailable.');
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
          <div style={{ fontSize: 22, fontWeight: 800, color: UI_COLORS.primary, marginBottom: 8 }}>
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
                  background: UI_COLORS.primary,
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
      background: 'linear-gradient(180deg, #f3f7fb 0%, #f8fafc 100%)', overflow: 'hidden',
    }}>
      {/* â”€â”€ Top hero bar â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div style={{
        background: 'linear-gradient(135deg, #081a2f 0%, #133457 58%, #1d4f7a 100%)',
        color: '#fff', padding: '16px 20px',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        flexShrink: 0,
        boxShadow: '0 12px 28px rgba(8, 26, 47, 0.16)',
      }}>
        <div>
          <div style={{ fontSize: 13, color: '#d8e6f2', maxWidth: 560, lineHeight: 1.45 }}>
            Govern ontology assets and expose traceable product knowledge across PLM, MBSE, and manufacturing.
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
              background: 'rgba(255,255,255,0.08)', color: '#fff',
              border: '1px solid rgba(154,217,226,0.3)',
              borderRadius: 10, padding: '7px 12px', fontSize: 11, fontWeight: 800, cursor: 'pointer',
            }}
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <RefreshCw size={12} />
              <span>Refresh</span>
            </span>
          </button>
        </div>
      </div>

      {/* â”€â”€ Main body: left panel (metrics + ontologies) + right (chat) â”€ */}
      <div style={{ flex: '1 1 0', minHeight: 0, display: 'flex', gap: 0, overflow: 'hidden' }}>

        {/* Left panel */}
        <div style={{
          width: 380, minWidth: 300, maxWidth: 460, flexShrink: 0,
          display: 'flex', flexDirection: 'column', gap: 0,
          borderRight: '1px solid rgba(139, 160, 184, 0.16)',
          background: 'rgba(255,255,255,0.84)',
          overflow: 'hidden',
          backdropFilter: 'blur(16px)',
        }}>

          {/* Ontology list */}
          <div style={{ flexShrink: 0, padding: '14px 14px', borderBottom: '1px solid rgba(139, 160, 184, 0.12)' }}>
            <SectionTitle>Ontology Registry</SectionTitle>
            {ontologiesError ? (
              <div role="alert" style={{ color: '#b42318', fontSize: 12, padding: 8 }}>
                {ontologiesError}
                <button type="button" onClick={loadOntologies} style={{ marginLeft: 8 }}>Retry</button>
              </div>
            ) : (
              <OntologyList ontologies={ontologies} loading={ontologiesLoading} />
            )}
          </div>

          {/* Ontology breakdown */}
          <div style={{ flex: '1 1 0', minHeight: 0, overflowY: 'auto', padding: '14px' }}>
            <SectionTitle>Graph Profile</SectionTitle>

            {metricsError ? (
              <div role="alert" style={{ color: '#b42318', fontSize: 12 }}>
                {metricsError}
                <button type="button" onClick={loadMetrics} style={{ marginLeft: 8 }}>Retry</button>
              </div>
            ) : metricsLoading ? (
              <div style={{ color: '#888', fontSize: 12 }}>Loading metrics...</div>
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
                {!metrics?.ontology_breakdown?.length && (
                  <BreakdownTable
                    title="Top Node Labels"
                    rows={metrics?.node_labels || []}
                    colKey="label"
                    colLabel="Count"
                  />
                )}
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
