import React, { useEffect, useState } from 'react';
import GraphHEB from '../Components/GraphHEB';
import GraphWidget from '../widgets/GraphWidget';
import { platformAPI } from '../services/apiClient';

function GraphServiceState({ state }) {
  const unavailable = state === 'not_configured';
  return (
    <section className="depo-panel" role="status" aria-live="polite" style={{ maxWidth: 760, margin: 'auto' }}>
      <div className="depo-panel__title">{unavailable ? 'Graph store setup required' : 'Graph Explorer is unavailable'}</div>
      <p className="depo-panel__meta">
        {unavailable
          ? 'Configure the selected graph-store connection, then refresh this page. Ontology and ingestion services remain available while graph visualization is offline.'
          : 'The graph service could not be reached. Start or configure the graph service, then refresh this page.'}
      </p>
    </section>
  );
}

export default function GraphExplorerPage(props) {
  const [serviceState, setServiceState] = useState({ loading: true, status: '' });

  useEffect(() => {
    const controller = new AbortController();
    platformAPI.health('graph', { signal: controller.signal, timeout: 5000 })
      .then((response) => setServiceState({ loading: false, status: String(response?.data?.status || 'ready').toLowerCase() }))
      .catch(() => setServiceState({ loading: false, status: 'unavailable' }));
    return () => controller.abort();
  }, []);

  if (serviceState.loading) {
    return <div className="depo-page-loading" role="status">Checking graph service…</div>;
  }

  if (['not_configured', 'offline', 'unavailable', 'error', 'failed'].includes(serviceState.status)) {
    return <div className="depo-page"><GraphServiceState state={serviceState.status} /></div>;
  }

  return (
    <div className="depo-page" style={{ height: '100%', minHeight: 'calc(100dvh - 120px)' }}>
      <GraphWidget minHeight={680}>
        <GraphHEB {...props} />
      </GraphWidget>
    </div>
  );
}
