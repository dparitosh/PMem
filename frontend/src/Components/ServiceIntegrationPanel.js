import React, { useCallback, useEffect, useState } from 'react';
import { IxButton, IxCard, IxCardContent, IxCardTitle } from '@siemens/ix-react';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';

const serviceUrl = (service, path) => buildSemanticServiceUrl(service, path);

function Detail({ label, value }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 12, padding: '4px 0' }}>
      <span style={{ color: '#52606d' }}>{label}</span>
      <span style={{ fontWeight: 700, textAlign: 'right' }}>{value}</span>
    </div>
  );
}

export default function ServiceIntegrationPanel() {
  const [state, setState] = useState({ loading: true, error: '', oslc: null, catalog: null, products: null });

  const load = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: '' }));
    const [oslc, catalog, products] = await Promise.allSettled([
      apiClient.get(serviceUrl('oslc', '/api/v1/oslc/health')),
      apiClient.get(serviceUrl('catalog', '/api/v1/catalog/products')),
      apiClient.get(serviceUrl('dataProducts', '/api/v1/data-products')),
    ]);
    const failed = [oslc, catalog, products]
      .filter((result) => result.status === 'rejected')
      .map((result) => result.reason?.response?.data?.detail || result.reason?.message)
      .filter(Boolean);
    setState({
      loading: false,
      error: failed.join(' · '),
      oslc: oslc.status === 'fulfilled' ? oslc.value.data : null,
      catalog: catalog.status === 'fulfilled' ? catalog.value.data : null,
      products: products.status === 'fulfilled' ? products.value.data : null,
    });
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <section aria-label="Platform service integrations" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 12, margin: '12px 0' }}>
      <IxCard variant="outline">
        <IxCardTitle>OSLC integration</IxCardTitle>
        <IxCardContent>
          <Detail label="Service" value={state.oslc?.status || (state.loading ? 'Checking' : 'Unavailable')} />
          <Detail label="Server" value={state.oslc?.server || '—'} />
          <Detail label="Remote provider" value={state.oslc?.remote_configured ? 'Configured' : 'Not configured'} />
        </IxCardContent>
      </IxCard>
      <IxCard variant="outline">
        <IxCardTitle>Data Catalog</IxCardTitle>
        <IxCardContent>
          <Detail label="Governed products" value={state.catalog?.count ?? '—'} />
          <Detail label="Endpoint" value="Catalog service" />
        </IxCardContent>
      </IxCard>
      <IxCard variant="outline">
        <IxCardTitle>Data Products</IxCardTitle>
        <IxCardContent>
          <Detail label="Published packages" value={state.products?.products?.length ?? '—'} />
          <Detail label="Endpoint" value="Data product service" />
          <IxButton variant="tertiary" onClick={load} disabled={state.loading}>Refresh integrations</IxButton>
        </IxCardContent>
      </IxCard>
      {state.error && <div role="status" style={{ gridColumn: '1 / -1', color: '#b12704', fontSize: 12 }}>{state.error}</div>}
    </section>
  );
}
