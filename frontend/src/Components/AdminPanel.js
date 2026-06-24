import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { RefreshCw, RotateCcw, Trash2 } from 'lucide-react';
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
  borderRadius: 5,
  background: '#fff',
  padding: 8,
};

const buttonStyle = {
  border: '1px solid #c8d3df',
  borderRadius: 5,
  background: '#fff',
  color: colors.text,
  fontSize: 12,
  fontWeight: 700,
  padding: '5px 8px',
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: 5,
};

function Stat({ label, value }) {
  return (
    <div style={{ minWidth: 82, padding: '5px 7px', borderLeft: `2px solid ${colors.blue}` }}>
      <div style={{ fontSize: 10, color: colors.muted, fontWeight: 800 }}>{label}</div>
      <div style={{ fontSize: 16, color: colors.text, fontWeight: 850, lineHeight: 1.2 }}>{value ?? '-'}</div>
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
  const [deleteLabel, setDeleteLabel] = useState('');
  const [deletePrefix, setDeletePrefix] = useState('');
  const [deleteProperty, setDeleteProperty] = useState('');
  const [deleteValue, setDeleteValue] = useState('');
  const [deleteBatchSize, setDeleteBatchSize] = useState(10000);
  const [deletePreview, setDeletePreview] = useState(null);

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

  const clearCache = useCallback(async () => {
    setLoading(true);
    setMessage('');
    setError('');
    try {
      const res = await API_METHODS.admin.clearCache();
      const cleared = res.data?.cleared || {};
      const parts = [
        cleared.graph_cache ? 'graph cache' : null,
        cleared.ontology_list_cache ? 'ontology list cache' : null,
        cleared.config_cache ? 'config cache' : null,
      ].filter(Boolean);
      setMessage(parts.length > 0
        ? `Cleared ${parts.join(', ')}.`
        : res.data?.message || 'Application caches cleared.');
      await loadAdminState();
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Cache clear failed.';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setLoading(false);
    }
  }, [loadAdminState]);

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
  const buildDeleteScope = useCallback(() => {
    const label = deleteLabel.trim();
    const prefix = deletePrefix.trim();
    const property = deleteProperty.trim();
    const value = deleteValue;
    const batchSize = Number(deleteBatchSize) || 10000;

    if (!label && !prefix) {
      return { error: 'Enter a Neo4j label or ontology prefix.' };
    }
    if (label && prefix) {
      return { error: 'Use either label or prefix, not both.' };
    }
    if ((property && value === '') || (!property && value !== '')) {
      return { error: 'Enter both property and value, or leave both empty.' };
    }

    const target = prefix
      ? property
        ? `prefix ${prefix} where ${property} = "${value}"`
        : `prefix ${prefix}`
      : property
        ? `label ${label} where ${property} = "${value}"`
        : `label ${label}`;

    return {
      request: {
        label,
        prefix,
        property,
        value,
        batchSize,
      },
      target,
      batchSize,
    };
  }, [deleteBatchSize, deleteLabel, deletePrefix, deleteProperty, deleteValue]);


  const deleteDataByLabel = useCallback(async () => {
    const scope = buildDeleteScope();
    if (scope.error) {
      setError(scope.error);
      return;
    }

    const ok = window.confirm(
      `Delete ${scope.target} in batches of ${scope.batchSize}? This cannot be undone.`
    );
    if (!ok) return;

    setLoading(true);
    setMessage('');
    setError('');
    try {
      const result = await API_METHODS.admin.deleteData(scope.request);
      const deleted = result?.data?.deleted_nodes ?? 0;
      const matched = result?.data?.matched_before ?? deleted;
      setMessage(`Deleted ${deleted} of ${matched} matched ${scope.target} node(s) using batched transactions.`);
      setDeletePreview(null);
      await loadAdminState();
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Batched delete failed.';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setLoading(false);
    }
  }, [buildDeleteScope, loadAdminState]);

  const previewDeleteData = useCallback(async () => {
    const scope = buildDeleteScope();
    if (scope.error) {
      setError(scope.error);
      return;
    }

    setLoading(true);
    setMessage('');
    setError('');
    try {
      const result = await API_METHODS.admin.deleteData({
        ...scope.request,
        dryRun: true,
      });
      const matched = result?.data?.matched_nodes ?? 0;
      setDeletePreview({ matched, target: scope.target, batchSize: scope.batchSize });
      setMessage(`Preview matched ${matched} node(s) for ${scope.target}. No data was deleted.`);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Delete preview failed.';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setLoading(false);
    }
  }, [buildDeleteScope]);

  const statusText = useMemo(() => {
    if (loading) return 'Refreshing';
    if (error) return 'Needs attention';
    if (health?.status) return 'Online';
    return 'Ready';
  }, [error, health, loading]);

  return (
    <div style={{ height: '100%', overflow: 'auto', background: '#fff', padding: 10 }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8 }}>
          <button type="button" onClick={loadAdminState} disabled={loading} style={buttonStyle}>
            <RefreshCw size={11} />
            Refresh
          </button>
        </div>

        <Message tone="success">{message}</Message>
        <Message tone="error">{error}</Message>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: 10 }}>
          <section style={cardStyle}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 850, color: colors.text }}>Service Health</div>
              <div style={{ fontSize: 13, fontWeight: 850, color: error ? colors.danger : colors.ok }}>
                {statusText}
              </div>
            </div>
            {health?.message && (
              <div style={{ fontSize: 11, color: colors.muted, marginTop: 3 }}>{health.message}</div>
            )}
          </section>

          <section style={cardStyle}>
            <div style={{ fontSize: 11, fontWeight: 850, color: colors.text, marginBottom: 6 }}>
              Neo4j Schema Snapshot
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(82px, 1fr))', gap: 4 }}>
              <Stat label="Nodes" value={stats?.total_nodes} />
              <Stat label="Rels" value={stats?.total_relationships} />
              <Stat label="Indexes" value={stats?.indexes_count} />
              <Stat label="Constraints" value={stats?.constraints_count} />
            </div>
          </section>
        </div>

        <section style={cardStyle}>
          <div style={{ fontSize: 11, fontWeight: 850, color: colors.text, marginBottom: 7 }}>
            Controlled Cleanup
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 6, marginBottom: 8 }}>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 10, fontWeight: 800, color: colors.muted }}>
              Label
              <input
                value={deleteLabel}
                onChange={(event) => setDeleteLabel(event.target.value)}
                placeholder="PRODUCT"
                style={{ border: `1px solid ${colors.border}`, borderRadius: 4, padding: '5px 6px', fontSize: 12 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 10, fontWeight: 800, color: colors.muted }}>
              Prefix
              <input
                value={deletePrefix}
                onChange={(event) => setDeletePrefix(event.target.value)}
                placeholder="ap239domain"
                style={{ border: `1px solid ${colors.border}`, borderRadius: 4, padding: '5px 6px', fontSize: 12 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 10, fontWeight: 800, color: colors.muted }}>
              Property
              <input
                value={deleteProperty}
                onChange={(event) => setDeleteProperty(event.target.value)}
                placeholder="import_id"
                style={{ border: `1px solid ${colors.border}`, borderRadius: 4, padding: '5px 6px', fontSize: 12 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 10, fontWeight: 800, color: colors.muted }}>
              Value
              <input
                value={deleteValue}
                onChange={(event) => setDeleteValue(event.target.value)}
                placeholder="required when property is set"
                style={{ border: `1px solid ${colors.border}`, borderRadius: 4, padding: '5px 6px', fontSize: 12 }}
              />
            </label>
            <label style={{ display: 'flex', flexDirection: 'column', gap: 3, fontSize: 10, fontWeight: 800, color: colors.muted }}>
              Batch size
              <input
                type="number"
                min="100"
                max="50000"
                step="100"
                value={deleteBatchSize}
                onChange={(event) => setDeleteBatchSize(event.target.value)}
                style={{ border: `1px solid ${colors.border}`, borderRadius: 4, padding: '5px 6px', fontSize: 12 }}
              />
            </label>
          </div>
          {deletePreview && (
            <div style={{ fontSize: 11, color: colors.muted, margin: '0 0 8px 0', fontWeight: 700 }}>
              Preview: {deletePreview.matched} node(s) match {deletePreview.target}. Batch size {deletePreview.batchSize}.
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <button
              type="button"
              onClick={clearCache}
              disabled={loading}
              style={buttonStyle}
            >
              <RotateCcw size={10} />
              Clear Cache
            </button>
            <button
              type="button"
              onClick={previewDeleteData}
              disabled={loading || (!deleteLabel.trim() && !deletePrefix.trim())}
              style={buttonStyle}
            >
              <RefreshCw size={10} />
              Preview Scope
            </button>
            <button
              type="button"
              onClick={deleteDataByLabel}
              disabled={loading || (!deleteLabel.trim() && !deletePrefix.trim())}
              style={{ ...buttonStyle, borderColor: '#ffb4a8', color: colors.danger }}
            >
              <Trash2 size={10} />
              Delete Scoped Nodes
            </button>
            <button type="button" onClick={deleteOldXsdSchemas} disabled={loading} style={buttonStyle}>
              <Trash2 size={10} />
              Delete Old XSD Schemas
            </button>
            <button
              type="button"
              onClick={cleanSchema}
              disabled={loading}
              style={{ ...buttonStyle, borderColor: '#ffb4a8', color: colors.danger }}
            >
              <Trash2 size={10} />
              Clean Neo4j Schema
            </button>
          </div>
        </section>
      </div>
    </div>
  );
}
