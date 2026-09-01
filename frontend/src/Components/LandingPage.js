import React, { useState, useEffect, useCallback } from 'react';
import { IxBadge, IxButton, IxCard, IxCardContent, IxCardTitle } from '@siemens/ix-react';
import { healthAPI } from '../services/apiClient';
import Chatbot from './Chatbot';
import ErrorBoundary from './ErrorBoundary';
import logger from '../utils/logger';
import { UI_COLORS } from '../styles/uiTokens';
import './LandingPage.css';

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

      <div className="ix-landing-page__workspace">
        <div className="ix-landing-page__insights">
          <IxCard variant="outline" className="ix-landing-page__card">
            <IxCardTitle>Ontology registry</IxCardTitle>
            <IxCardContent>
              {ontologiesError ? <div role="alert" className="ix-landing-page__alert">{ontologiesError}<IxButton type="button" variant="tertiary" onClick={loadOntologies}>Retry</IxButton></div> : <OntologyList ontologies={ontologies} loading={ontologiesLoading} />}
            </IxCardContent>
          </IxCard>
          <IxCard variant="outline" className="ix-landing-page__card ix-landing-page__profile">
            <IxCardTitle>Graph profile</IxCardTitle>
            <IxCardContent>
              {metricsError ? <div role="alert" className="ix-landing-page__alert">{metricsError}<IxButton type="button" variant="tertiary" onClick={loadMetrics}>Retry</IxButton></div> : metricsLoading ? <div className="ix-landing-page__empty">Loading graph metrics…</div> : metrics?.ontology_breakdown?.length > 0 ? <BreakdownTable title="Nodes by ontology / source" rows={metrics.ontology_breakdown} colKey="ontology" colLabel="Nodes" /> : <BreakdownTable title="Top node labels" rows={metrics?.node_labels || []} colKey="label" colLabel="Count" />}
            </IxCardContent>
          </IxCard>
        </div>
        <IxCard variant="outline" className="ix-landing-page__chat">
          <IxCardTitle>Knowledge companion</IxCardTitle>
          <IxCardContent>
            <ErrorBoundary><Chatbot setChatResults={setChatResults} /></ErrorBoundary>
          </IxCardContent>
        </IxCard>
      </div>
    </div>
  );
}
