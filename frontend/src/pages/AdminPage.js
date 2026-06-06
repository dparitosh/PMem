import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Bot } from 'lucide-react';
import AdminPanel from '../Components/AdminPanel';
import { API_METHODS } from '../services/apiClient';
import KpiStrip from '../widgets/KpiStrip';
import PageHeader from '../widgets/PageHeader';
import RegistryWidget from '../widgets/RegistryWidget';
import { widgetCardStyle, widgetColors } from '../widgets/widgetStyles';

const routeColumns = [
  { field: 'method', width: 100 },
  { field: 'path', flex: 2 },
  { field: 'tag', flex: 1 },
  { field: 'service_group', flex: 1 },
  { field: 'frontend_mapped', headerName: 'Frontend Mapped', width: 150 },
];

const serviceColumns = [
  { field: 'id', width: 170 },
  { field: 'name', flex: 1.5, minWidth: 210 },
  { field: 'type', width: 150 },
  { field: 'status', width: 120 },
  { field: 'owner', width: 170 },
  { field: 'endpoint', flex: 1.4, minWidth: 190 },
  { field: 'health_endpoint', headerName: 'Health Endpoint', flex: 1, minWidth: 160 },
  { field: 'route_count', headerName: 'Routes', width: 105 },
  { field: 'frontend_mapped_count', headerName: 'Mapped', width: 110 },
  { field: 'database', width: 125 },
  { field: 'configured_database', headerName: 'Configured DB', width: 140 },
  { field: 'config_source', headerName: 'Config Source', flex: 1, minWidth: 160 },
  { field: 'model', width: 150 },
];

const dataSourceColumns = [
  { field: 'id', width: 120 },
  { field: 'name', flex: 1.2, minWidth: 210 },
  { field: 'type', width: 150 },
  { field: 'status', width: 120 },
  { field: 'uri_masked', headerName: 'URI', flex: 1.2, minWidth: 180 },
  { field: 'active_database', headerName: 'Active DB', width: 130 },
  { field: 'configured_database', headerName: 'Configured DB', width: 140 },
  { field: 'configured_database_source', headerName: 'Config Source', flex: 1, minWidth: 170 },
  { field: 'database_status', headerName: 'DB Status', width: 125 },
  { field: 'deployment_type', headerName: 'Deployment', width: 130 },
  { field: 'encrypted', width: 110 },
  { field: 'query_timeout', headerName: 'Timeout', width: 110 },
  { field: 'message', flex: 1.6, minWidth: 220 },
  { field: 'mutable', width: 100 },
];

const configColumns = [
  { field: 'component', width: 120 },
  { field: 'key', width: 170 },
  { field: 'configured_value', headerName: 'Configured Value', flex: 1.3, minWidth: 180 },
  { field: 'active_value', headerName: 'Active Value', flex: 1.2, minWidth: 170 },
  { field: 'source', flex: 1.1, minWidth: 170 },
  { field: 'status', width: 120 },
  { field: 'mutable', width: 100 },
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
    config: registry?.configuration?.length || 0,
  }), [registry]);

  return (
    <div className="depo-page">
      <PageHeader
        eyebrow="Operations and platform registry"
        title="Operate services, datasources, agents, and workflow capabilities from one catalog"
        summary="Admin is the control room for runtime health and governed capabilities. Destructive actions stay isolated in Operations; registry data remains read-only for this phase."
        insights={[
          { label: 'Service standard', value: 'Every runtime has owner, endpoint, status, and health path' },
          { label: 'Governance rule', value: 'Frontend never connects directly to Neo4j' },
          { label: 'Change scope', value: 'Read-only registry first; config writes stay deferred' },
        ]}
      />
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
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

      <KpiStrip
        items={[
          { label: 'Services', value: counts.services },
          { label: 'API routes', value: counts.routes },
          { label: 'Datasources', value: counts.sources },
          { label: 'Configuration', value: counts.config },
          { label: 'Workflow capabilities', value: counts.workflows },
        ]}
      />

      <div className="depo-two-column">
        <section className="depo-panel">
          <div className="depo-panel__header">
            <div>
              <div className="depo-panel__title">Operations</div>
              <div className="depo-panel__meta">Controlled cleanup and current Neo4j schema status.</div>
            </div>
          </div>
          <AdminPanel onSchemaCleaned={onSchemaCleaned} />
        </section>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <RegistryWidget title="Service Catalog" rows={registry?.services || []} columns={serviceColumns} height={320} />
          <RegistryWidget title="Data Sources" rows={registry?.data_sources || []} columns={dataSourceColumns} height={250} />
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

      <RegistryWidget title="Runtime Configuration" rows={registry?.configuration || []} columns={configColumns} height={300} />
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
