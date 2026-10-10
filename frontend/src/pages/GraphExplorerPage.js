import React, { useEffect, useState } from 'react';
import GraphHEB from '../Components/GraphHEB';
import GraphWidget from '../widgets/GraphWidget';
import { platformAPI } from '../services/apiClient';

function GraphServiceState({ state, retry }) {
  const unavailable = state === 'not_configured';
  const unauthorized = state === 'unauthorized';
  return (
    <section className="depo-panel" role="status" aria-live="polite" style={{ maxWidth: 760, margin: 'auto' }}>
      <div className="depo-panel__title">{unauthorized ? 'Graph access required' : unavailable ? 'Graph store setup required' : 'Graph Explorer is unavailable'}</div>
      <p className="depo-panel__meta">
        {unauthorized ? 'Connect or validate graph read access in Admin, then retry.' : unavailable
          ? 'Configure the selected graph-store connection, then refresh this page. Ontology and ingestion services remain available while graph visualization is offline.'
          : 'The graph service could not be reached. Start or configure the graph service, then refresh this page.'}
      </p>
      <button type="button" className="depo-button" onClick={retry}>Retry graph connection</button>
    </section>
  );
}

export default function GraphExplorerPage(props) {
  const [revision, setRevision] = useState(0);
  const [serviceState, setServiceState] = useState({ loading: true, status: '' });

  useEffect(() => {
    setServiceState({ loading: true, status: '' });
    const controller = new AbortController();
    platformAPI.health('graph', { signal: controller.signal, timeout: 5000 })
      .then((response) => !controller.signal.aborted && setServiceState({ loading: false, status: String(response?.data?.status || 'unavailable').toLowerCase() }))
      .catch(error => !controller.signal.aborted && setServiceState({ loading: false, status: [401, 403].includes(error?.response?.status) ? 'unauthorized' : 'unavailable' }));
    return () => controller.abort();
  }, [revision]);

  if (serviceState.loading) {
    return <div className="depo-page-loading" role="status">Checking graph service…</div>;
  }

  if (!['ok', 'ready', 'healthy'].includes(serviceState.status)) {
    return <div className="depo-page"><GraphServiceState state={serviceState.status} retry={() => setRevision(value => value + 1)} /></div>;
  }

  return (
    <div className="depo-page" style={{ height: '100%', minHeight: 'calc(100dvh - 120px)' }}>
      <GraphWidget minHeight={680}>
        <GraphHEB {...props} />
      </GraphWidget>
    </div>
  );
}
