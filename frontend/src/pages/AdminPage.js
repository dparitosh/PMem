import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Bot, Database, Route, Server, Workflow } from 'lucide-react';
import AdminPanel from '../Components/AdminPanel';
import { API_METHODS } from '../services/apiClient';
import RegistryWidget from '../widgets/RegistryWidget';
import StatWidget from '../widgets/StatWidget';
import { widgetCardStyle, widgetColors } from '../widgets/widgetStyles';

const routeColumns = [
  { field: 'method', width: 100 },
  { field: 'path', flex: 2 },
  { field: 'tag', flex: 1 },
  { field: 'service_group', flex: 1 },
  { field: 'frontend_mapped', headerName: 'Frontend Mapped', width: 150 },
];

const packageColumns = [
  { field: 'name', flex: 1.4 },
  { field: 'category', flex: 1 },
  { field: 'used', width: 110 },
  { field: 'recommendation', flex: 1 },
];

export default function AdminPage({ onSchemaCleaned }) {
  const [registry, setRegistry] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const loadRegistry = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await API_METHODS.admin.registry();
      setRegistry(response.data);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Admin registry is unavailable.';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadRegistry();
  }, [loadRegistry]);

  const counts = useMemo(() => ({
    services: registry?.services?.length || 0,
    routes: registry?.api_routes?.length || 0,
    sources: registry?.data_sources?.length || 0,
    workflows: registry?.workflows?.length || 0,
  }), [registry]);

  return (
    <div className="depo-page">
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div>
          <div style={{ color: widgetColors.text, fontSize: 18, fontWeight: 850 }}>Admin Registry</div>
          <div style={{ color: widgetColors.muted, fontSize: 12 }}>Read-only service catalog, API routes, datasources, agents, workflows, and package guidance.</div>
        </div>
        <button
          type="button"
          onClick={loadRegistry}
          disabled={loading}
          style={{
            border: `1px solid ${widgetColors.blue}`,
            background: '#fff',
            color: widgetColors.blue,
            borderRadius: 5,
            fontSize: 12,
            fontWeight: 800,
            padding: '7px 10px',
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          Refresh Registry
        </button>
      </div>

      {error && (
        <div style={{ ...widgetCardStyle, padding: 10, color: widgetColors.danger, fontSize: 12, fontWeight: 700 }}>
          {error}
        </div>
      )}

      <div className="depo-widget-grid">
        <StatWidget label="Services" value={counts.services} icon={Server} status={counts.services ? 'ok' : 'neutral'} />
        <StatWidget label="API Routes" value={counts.routes} icon={Route} status={counts.routes ? 'ok' : 'neutral'} />
        <StatWidget label="Datasources" value={counts.sources} icon={Database} status={counts.sources ? 'ok' : 'neutral'} />
        <StatWidget label="Workflows" value={counts.workflows} icon={Workflow} status={counts.workflows ? 'ok' : 'neutral'} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 0.85fr) minmax(0, 1.15fr)', gap: 12, alignItems: 'start' }}>
        <AdminPanel onSchemaCleaned={onSchemaCleaned} />
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <RegistryWidget title="Service Catalog" rows={registry?.services || []} height={240} />
          <RegistryWidget title="Data Sources" rows={registry?.data_sources || []} height={220} />
          <RegistryWidget title="Agents" rows={registry?.agents || []} height={220} columns={[
            { field: 'id', flex: 1 },
            { field: 'name', flex: 1.4 },
            { field: 'provider' },
            { field: 'model', flex: 1.2 },
            { field: 'status' },
            { field: 'health_endpoint', flex: 1.4 },
          ]} />
        </div>
      </div>

      <RegistryWidget title="Workflow Registry" rows={registry?.workflows || []} height={280} />
      <RegistryWidget title="API Route Registry" rows={registry?.api_routes || []} columns={routeColumns} height={360} />
      <RegistryWidget title="Package Rationalization" rows={registry?.packages || []} columns={packageColumns} height={360} />

      <div style={{ ...widgetCardStyle, padding: 10, display: 'flex', gap: 8, alignItems: 'center', color: widgetColors.muted, fontSize: 12 }}>
        <Bot size={14} color={widgetColors.blue} />
        Configuration editing APIs are intentionally deferred; this version is a read-only operational catalog.
      </div>
    </div>
  );
}
