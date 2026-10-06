import React, { useCallback, useEffect, useRef, useState } from 'react';
import { IxButton } from '@siemens/ix-react';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';

const serviceUrl = (service, path) => buildSemanticServiceUrl(service, path);

function collectionTotal(data) {
  if (!data || !Array.isArray(data.products)) throw new Error('Product service returned an invalid collection.');
  const total = data.total ?? (data.next_offset == null ? data.products.length : null);
  if (!Number.isSafeInteger(total) || total < data.products.length) throw new Error('Product service returned an invalid total.');
  return total;
}

function collectionRequest(service, path, signal) {
  return apiClient.get(serviceUrl(service, path), { signal }).then(response => ({
    data: { ...response.data, total: collectionTotal(response.data) },
  })).catch(error => {
    const status = error.response?.status;
    const name = service === 'catalog' ? 'Data Catalog' : 'Data Products';
    if (status === 401 || status === 403) throw new Error(`${name}: access denied (${status}). Reconnect the Admin session with graph-read permission.`);
    throw new Error(`${name}: ${error.message || 'Unable to load products.'}`);
  });
}

function Detail({ label, value }) {
  return (
    <div className="depo-card-detail">
      <span className="depo-card-detail__label">{label}</span>
      <span className="depo-card-detail__value">{value}</span>
    </div>
  );
}

export default function ServiceIntegrationPanel() {
  const [state, setState] = useState({ loading: true, error: '', oslc: null, catalog: null, products: null });

  const requestRef = useRef(null);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setState({ loading: true, error: '', oslc: null, catalog: null, products: null });
    const [oslc, catalog, products] = await Promise.allSettled([
      Promise.resolve().then(() => apiClient.get(serviceUrl('oslc', '/api/v1/oslc/health'), { signal: controller.signal })),
      Promise.resolve().then(() => collectionRequest('catalog', '/api/v1/catalog/products', controller.signal)),
      Promise.resolve().then(() => collectionRequest('dataProducts', '/api/v1/data-products', controller.signal)),
    ]);
    if (controller.signal.aborted) return;
    const failed = [oslc, catalog, products]
      .filter((result) => result.status === 'rejected')
      .map((result) => {
        const detail = result.reason?.response?.data?.detail || result.reason?.message;
        return typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : '';
      })
      .filter(Boolean);
    setState({
      loading: false,
      error: failed.join(' · '),
      oslc: oslc.status === 'fulfilled' ? oslc.value.data : null,
      catalog: catalog.status === 'fulfilled' ? catalog.value.data : null,
      products: products.status === 'fulfilled' ? products.value.data : null,
    });
  }, []);

  useEffect(() => {
    load();
    window.addEventListener('depo:credentials-changed', load);
    window.addEventListener('depo:credentials-cleared', load);
    return () => {
      requestRef.current?.abort();
      window.removeEventListener('depo:credentials-changed', load);
      window.removeEventListener('depo:credentials-cleared', load);
    };
  }, [load]);

  return (
    <section aria-label="Platform service integrations" className="depo-service-integrations">
      <article className="depo-service-card">
        <h3>OSLC integration</h3>
        <div className="depo-service-card__body">
          <Detail label="Service" value={state.oslc?.status || (state.loading ? 'Checking' : 'Unavailable')} />
          <Detail label="Server" value={state.oslc?.server || '—'} />
          <Detail label="Remote provider" value={state.oslc?.remote_configured ? 'Configured' : 'Not configured'} />
        </div>
      </article>
      <article className="depo-service-card">
        <h3>Data Catalog</h3>
        <div className="depo-service-card__body">
          <Detail label="Governed product versions" value={state.catalog?.total ?? state.catalog?.count ?? '—'} />
          <Detail label="Endpoint" value="Catalog service" />
          {!state.loading && state.catalog?.total === 0 && <p>No governed product versions are registered in this catalog.</p>}
        </div>
      </article>
      <article className="depo-service-card">
        <h3>Data Products</h3>
        <div className="depo-service-card__body">
          <Detail label="Retained packages" value={state.products?.total ?? state.products?.products?.length ?? '—'} />
          <Detail label="Endpoint" value="Data product service" />
          {!state.loading && state.products?.total === 0 && <p>No packages have been retained. Publish an approved data-product draft to create one.</p>}
          <IxButton variant="tertiary" onClick={load} disabled={state.loading}>Refresh integrations</IxButton>
        </div>
      </article>
      {state.error && <div role="status" className="depo-service-integrations__error">{state.error}</div>}
    </section>
  );
}
