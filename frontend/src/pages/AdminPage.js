import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bot } from 'lucide-react';
import AdminPanel from '../Components/AdminPanel';
import { API_METHODS } from '../services/apiClient';
import agenticAPI from '../services/agenticApi';
import KpiStrip from '../widgets/KpiStrip';
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
  { field: 'config_source', headerName: 'Config Source', flex: 1, minWidth: 160 },
  { field: 'route_count', headerName: 'Routes', width: 105 },
  { field: 'frontend_mapped_count', headerName: 'Mapped', width: 110 },
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
  const agenticEnabled = agenticAPI.isEnabled();
  const agenticConfigured = agenticAPI.isConfigured();
  const [registry, setRegistry] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [agenticCatalog, setAgenticCatalog] = useState(null);
  const [agenticLoading, setAgenticLoading] = useState(false);
  const [agenticError, setAgenticError] = useState('');
  const [openApiCatalog, setOpenApiCatalog] = useState(null);
  const [openApiLoading, setOpenApiLoading] = useState(false);
  const registryControllerRef = useRef(null);
  const agenticControllerRef = useRef(null);

  const loadRegistry = useCallback(async () => {
    registryControllerRef.current?.abort();
    const controller = new AbortController();
    registryControllerRef.current = controller;
    setLoading(true);
    setError('');
    try {
      const response = await API_METHODS.admin.registry({ signal: controller.signal });
      setRegistry(response.data);
    } catch (err) {
      if (controller.signal.aborted) return;
      const detail = err?.response?.data?.detail || err?.message || 'Admin registry is unavailable.';
      setError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
      if (registryControllerRef.current === controller) registryControllerRef.current = null;
    }
  }, []);

  useEffect(() => {
    loadRegistry();
    return () => registryControllerRef.current?.abort();
  }, [loadRegistry]);

  const loadAgenticCatalog = useCallback(async () => {
    agenticControllerRef.current?.abort();
    if (!agenticEnabled) {
      setAgenticCatalog(null);
      setAgenticError('');
      return;
    }
    if (!agenticConfigured) {
      setAgenticCatalog(null);
      setAgenticError('Agentic components are enabled, but REACT_APP_AGENTIC_SERVICE_URL is not configured.');
      return;
    }
    const controller = new AbortController();
    agenticControllerRef.current = controller;
    setAgenticLoading(true);
    setAgenticError('');
    try {
      const [agentsResponse, toolsResponse] = await Promise.all([
        agenticAPI.listAgents({ signal: controller.signal }),
        agenticAPI.listTools({ signal: controller.signal }),
      ]);
      if (controller.signal.aborted) return;
      setAgenticCatalog({
        agents: agentsResponse.data?.agents || [],
        tools: toolsResponse.data?.tools || [],
        invalidExports: toolsResponse.data?.invalid_exports || [],
      });
    } catch (err) {
      if (controller.signal.aborted) return;
      const detail = err?.response?.data?.detail || err?.message || 'Agentic component catalog is unavailable.';
      setAgenticError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      if (!controller.signal.aborted) setAgenticLoading(false);
      if (agenticControllerRef.current === controller) agenticControllerRef.current = null;
    }
  }, [agenticConfigured, agenticEnabled]);

  useEffect(() => {
    loadAgenticCatalog();
    return () => agenticControllerRef.current?.abort();
  }, [loadAgenticCatalog]);

  const importOpenApi = useCallback(async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!agenticConfigured) {
      setAgenticError(agenticEnabled
        ? 'Agentic component adapter is not configured.'
        : 'Agentic components are disabled by configuration.');
      return;
    }
    setOpenApiLoading(true);
    setAgenticError('');
    try {
      const document = JSON.parse(await file.text());
      const response = await agenticAPI.importOpenApi(document, file.name);
      setOpenApiCatalog(response.data);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'OpenAPI import failed.';
      setAgenticError(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setOpenApiLoading(false);
    }
  }, [agenticConfigured, agenticEnabled]);

  const counts = useMemo(() => ({
    services: registry?.services?.length || 0,
    routes: registry?.api_routes?.length || 0,
    sources: registry?.data_sources?.length || 0,
    agents: registry?.agents?.length || 0,
    packages: registry?.packages?.length || 0,
    workflows: registry?.workflows?.length || 0,
    config: registry?.configuration?.length || 0,
  }), [registry]);
  const secondaryCatalogs = [
    {
      title: 'Agents',
      count: counts.agents,
      height: 220,
      rows: registry?.agents || [],
      columns: [
        { field: 'id', flex: 1 },
        { field: 'name', flex: 1.4 },
        { field: 'provider' },
        { field: 'model', flex: 1.2 },
        { field: 'status' },
        { field: 'health_endpoint', flex: 1.4 },
        { field: 'config_source', flex: 1 },
      ],
    },
    {
      title: 'Runtime Configuration',
      count: counts.config,
      height: 300,
      rows: registry?.configuration || [],
      columns: configColumns,
    },
    {
      title: 'Workflow Registry',
      count: counts.workflows,
      height: 280,
      rows: registry?.workflows || [],
    },
    {
      title: 'API Route Registry',
      count: counts.routes,
      height: 360,
      rows: registry?.api_routes || [],
      columns: routeColumns,
    },
    {
      title: 'Package Rationalization',
      count: counts.packages,
      height: 360,
      rows: registry?.packages || [],
      columns: packageColumns,
    },
  ];

  return (
    <div className="depo-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 12, color: widgetColors.muted, lineHeight: 1.4, maxWidth: 720 }}>
          Registry tables are read-only operational views. Use the maintenance panel for cache, targeted graph cleanup, ontology metadata cleanup, and reset actions.
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

      <KpiStrip
        items={[
          { label: 'Services', value: counts.services },
          { label: 'API routes', value: counts.routes },
          { label: 'Datasources', value: counts.sources },
          { label: 'Agents', value: counts.agents },
          { label: 'Configuration', value: counts.config },
          { label: 'Workflows', value: counts.workflows },
        ]}
      />

      <section className="depo-panel" style={{ marginBottom: 12 }}>
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Agentic Components</div>
            <div className="depo-panel__meta">
              {agenticEnabled
                ? 'Tool contracts and agent specifications available to a low-code/no-code orchestrator.'
                : 'Disabled. Set REACT_APP_AGENTIC_ENABLED=true and restart the frontend to enable this optional service.'}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            <label className="depo-button depo-button--secondary" style={{ cursor: openApiLoading ? 'wait' : 'pointer', opacity: agenticConfigured ? 1 : 0.55 }}>
              {openApiLoading ? 'Importing OpenAPI...' : 'Import OpenAPI JSON'}
              <input type="file" accept="application/json,.json" onChange={importOpenApi} disabled={openApiLoading || !agenticConfigured} style={{ display: 'none' }} />
            </label>
            <button type="button" className="depo-button depo-button--secondary" onClick={loadAgenticCatalog} disabled={agenticLoading || !agenticConfigured}>
              {agenticLoading ? 'Loading...' : 'Refresh'}
            </button>
          </div>
        </div>
        {agenticError && <div className="depo-alert depo-alert--warning">{agenticError}</div>}
        {agenticCatalog && (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(180px, 0.7fr) minmax(300px, 1.3fr)', gap: 12 }}>
            <RegistryWidget
              title={`Agents (${agenticCatalog.agents.length})`}
              rows={agenticCatalog.agents}
              columns={[{ field: 'name', flex: 1.2 }, { field: 'handler_name', flex: 1 }, { field: 'use_case', flex: 1.5 }]}
              height={250}
            />
            <RegistryWidget
              title={`Tools (${agenticCatalog.tools.length})`}
              rows={agenticCatalog.tools}
              columns={[{ field: 'name', flex: 1.5 }, { field: 'category', width: 120 }, { field: 'side_effect', width: 140 }, { field: 'requires_approval', headerName: 'Approval', width: 100 }]}
              height={250}
            />
          </div>
        )}
        {openApiCatalog && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginTop: 12 }}>
            <span className="depo-badge">
              {openApiCatalog.title} · {openApiCatalog.summary?.operations || 0} operations · {openApiCatalog.summary?.schemas || 0} schemas
            </span>
          </div>
        )}
        {openApiCatalog?.operations?.length > 0 && (
          <div style={{ marginTop: 10 }}>
            <RegistryWidget
              title="Imported OpenAPI operations"
              rows={openApiCatalog.operations}
              columns={[{ field: 'method', width: 90 }, { field: 'path', flex: 1.4 }, { field: 'operation_id', flex: 1 }, { field: 'summary', flex: 2 }]}
              height={240}
            />
          </div>
        )}
      </section>

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
        </div>
      </div>

      <details style={{ ...widgetCardStyle, padding: 12 }}>
        <summary style={{ cursor: 'pointer', color: widgetColors.text, fontSize: 14, fontWeight: 800 }}>
          Additional catalogs
        </summary>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8, marginTop: 12 }}>
          {secondaryCatalogs.map((catalog) => (
            <div
              key={`summary-${catalog.title}`}
              style={{
                border: `1px solid ${widgetColors.border}`,
                borderRadius: 10,
                padding: '10px 12px',
                background: '#f8fafc',
              }}
            >
              <div style={{ fontSize: 11, color: widgetColors.muted, marginBottom: 4 }}>{catalog.title}</div>
              <div style={{ fontSize: 20, fontWeight: 800, color: widgetColors.text }}>{catalog.count}</div>
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 12 }}>
          {secondaryCatalogs.map((catalog) => (
            <details key={catalog.title} style={{ border: `1px solid ${widgetColors.border}`, borderRadius: 10, padding: 10, background: '#fff' }}>
              <summary style={{ cursor: 'pointer', color: widgetColors.text, fontSize: 13, fontWeight: 800 }}>
                {catalog.title} ({catalog.count})
              </summary>
              <div style={{ marginTop: 10 }}>
                <RegistryWidget
                  title={catalog.title}
                  rows={catalog.rows}
                  columns={catalog.columns}
                  height={catalog.height}
                />
              </div>
            </details>
          ))}
        </div>
      </details>

      <div style={{ ...widgetCardStyle, padding: 10, display: 'flex', gap: 8, alignItems: 'center', color: widgetColors.muted, fontSize: 12 }}>
        <Bot size={14} color={widgetColors.blue} />
        Configuration editing APIs are intentionally deferred; this version is a read-only operational catalog.
      </div>
    </div>
  );
}
