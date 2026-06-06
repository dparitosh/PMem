import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Database, RefreshCw, Server, Trash2 } from 'lucide-react';
import { API_METHODS } from '../services/apiClient';
import { useOntologies } from '../contexts/OntologyContext';

const colors = {
  blue: '#004B87',
  border: '#d9e2ec',
  text: '#243b53',
  muted: '#52606d',
  bg: '#f7f9fb',
  danger: '#b42318',
  dangerBg: '#fff1f0',
  ok: '#1f7a4d',
};

const cardStyle = {
  border: `1px solid ${colors.border}`,
  borderRadius: 6,
  background: '#fff',
  padding: 14,
};

const buttonStyle = {
  border: '1px solid #c8d3df',
  borderRadius: 5,
  background: '#fff',
  color: colors.text,
  fontSize: 12,
  fontWeight: 700,
  padding: '7px 10px',
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 6,
};

function Stat({ label, value }) {
  return (
    <div style={{ minWidth: 120, padding: '6px 8px', borderLeft: `3px solid ${colors.blue}` }}>
      <div style={{ fontSize: 11, color: colors.muted, fontWeight: 700 }}>{label}</div>
      <div style={{ fontSize: 22, color: colors.text, fontWeight: 800, lineHeight: 1.2 }}>{value ?? '-'}</div>
    </div>
  );
}

function Message({ tone, children }) {
  if (!children) return null;
  const isError = tone === 'error';
  return (
    <div
      style={{
        border: `1px solid ${isError ? '#ffccc7' : '#b7ebc6'}`,
        background: isError ? colors.dangerBg : '#f0fff4',
        color: isError ? colors.danger : colors.ok,
        borderRadius: 6,
        padding: '8px 10px',
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {children}
    </div>
  );
}

export default function AdminPanel({ onSchemaCleaned }) {
  const { fetchOntologies } = useOntologies();
  const [health, setHealth] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const loadAdminState = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [healthRes, statsRes] = await Promise.allSettled([
        API_METHODS.admin.health(),
        API_METHODS.admin.schemaStats(),
      ]);
      if (healthRes.status === 'fulfilled') {
        setHealth(healthRes.value.data || null);
      } else {
        const detail =
          healthRes.reason?.response?.data?.detail ||
          healthRes.reason?.message ||
          'Admin health unavailable.';
        setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
      }
      if (statsRes.status === 'fulfilled') {
        setStats(statsRes.value.data?.stats || null);
      } else {
        const detail =
          statsRes.reason?.response?.data?.detail ||
          statsRes.reason?.message ||
          'Unable to load Neo4j schema stats.';
        setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAdminState();
  }, [loadAdminState]);

  const cleanSchema = useCallback(async () => {
    const ok = window.confirm(
      'Clean Neo4j schema? This will delete all nodes, relationships, uploaded ontology metadata, indexes, and constraints.'
    );
    if (!ok) return;

    setLoading(true);
    setMessage('');
    setError('');
    try {
      const res = await API_METHODS.admin.cleanSchema();
      const metadataCleared = res.data?.metadata_cleared ?? 0;
      setMessage(`${res.data?.message || 'Schema cleanup completed.'} Ontology folders cleared: ${metadataCleared}.`);
      await fetchOntologies();
      window.dispatchEvent(new Event('dt-schema-cleaned'));
      if (typeof onSchemaCleaned === 'function') onSchemaCleaned();
      await loadAdminState();
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Schema cleanup failed.';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setLoading(false);
    }
  }, [fetchOntologies, loadAdminState, onSchemaCleaned]);

  const deleteOldXsdSchemas = useCallback(async () => {
    setLoading(true);
    setMessage('');
    setError('');
    try {
      const preview = await API_METHODS.ontology.cleanupOldXsd({
        dry_run: true,
        delete_from_neo4j: true,
      });
      const count = preview?.data?.candidate_count || 0;
      if (count === 0) {
        setMessage('No old ingested XSD schemas found to delete.');
        return;
      }

      const ok = window.confirm(`Delete ${count} old ingested XSD schema entries from storage and Neo4j?`);
      if (!ok) return;

      const result = await API_METHODS.ontology.cleanupOldXsd({
        dry_run: false,
        delete_from_neo4j: true,
        confirm: 'DELETE_OLD_XSD',
      });
      const deleted = result?.data?.deleted_count || 0;
      const deletedNodes = result?.data?.neo4j_deleted_nodes || 0;
      setMessage(`Deleted ${deleted} old XSD schema entries and ${deletedNodes} Neo4j nodes.`);
      await fetchOntologies();
      await loadAdminState();
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Old XSD cleanup failed.';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setLoading(false);
    }
  }, [fetchOntologies, loadAdminState]);

  const statusText = useMemo(() => {
    if (loading) return 'Refreshing';
    if (error) return 'Needs attention';
    if (health?.status) return 'Online';
    return 'Ready';
  }, [error, health, loading]);

  return (
    <div style={{ height: '100%', overflow: 'auto', background: '#fff', padding: 10 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 12 }}>
          <button type="button" onClick={loadAdminState} disabled={loading} style={buttonStyle}>
            <RefreshCw size={14} />
            Refresh
          </button>
        </div>

        <Message tone="success">{message}</Message>
        <Message tone="error">{error}</Message>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 10 }}>
          <section style={{ ...cardStyle, padding: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <Server size={16} color={colors.blue} />
              <div style={{ fontSize: 13, fontWeight: 800, color: colors.text }}>Service Health</div>
            </div>
            <div style={{ fontSize: 20, fontWeight: 850, color: error ? colors.danger : colors.ok }}>
              {statusText}
            </div>
            {health?.message && (
              <div style={{ fontSize: 12, color: colors.muted, marginTop: 4 }}>{health.message}</div>
            )}
          </section>

          <section style={{ ...cardStyle, padding: 10 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
              <Database size={16} color={colors.blue} />
              <div style={{ fontSize: 13, fontWeight: 800, color: colors.text }}>Neo4j Schema Snapshot</div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: 8 }}>
              <Stat label="Nodes" value={stats?.total_nodes} />
              <Stat label="Relationships" value={stats?.total_relationships} />
              <Stat label="Custom indexes" value={stats?.indexes_count} />
              <Stat label="Constraints" value={stats?.constraints_count} />
            </div>
          </section>
        </div>

        <section style={{ ...cardStyle, padding: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
            <AlertTriangle size={16} color={colors.danger} />
            <div style={{ fontSize: 13, fontWeight: 800, color: colors.text }}>Controlled Cleanup</div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button type="button" onClick={deleteOldXsdSchemas} disabled={loading} style={buttonStyle}>
              <Trash2 size={14} />
              Delete Old XSD Schemas
            </button>
            <button
              type="button"
              onClick={cleanSchema}
              disabled={loading}
              style={{ ...buttonStyle, borderColor: '#ffb4a8', color: colors.danger }}
            >
              <Trash2 size={14} />
              Clean Neo4j Schema
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
