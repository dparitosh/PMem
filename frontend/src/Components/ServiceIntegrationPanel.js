import React, { useCallback, useEffect, useRef, useState } from 'react';
import { IxButton } from '@siemens/ix-react';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import FirstProductGuide from './FirstProductGuide';
import { readProductCollection, PRODUCT_REFRESH_MS, PRODUCT_CHANGED_EVENT } from '../services/productService';

const serviceUrl = (service, path) => buildSemanticServiceUrl(service, path);

function collectionRequest(service, path, signal) {
  return readProductCollection(service, signal).then(collection => ({
    data: { products: collection.rows, total: collection.total, warning: collection.warning },
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
      Promise.resolve().then(() => apiClient.get(serviceUrl('oslc', '/api/v1/oslc/health'), { signal: controller.signal, timeout: 15000 })),
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
    if (requestRef.current === controller) requestRef.current = null;
  }, []);

  useEffect(() => {
    load();
    const interval = window.setInterval(() => { if (!document.hidden && !requestRef.current) load(); }, PRODUCT_REFRESH_MS);
    window.addEventListener(PRODUCT_CHANGED_EVENT, load);
    window.addEventListener('depo:credentials-changed', load);
    window.addEventListener('depo:credentials-cleared', load);
    return () => {
      requestRef.current?.abort();
      window.clearInterval(interval);
      window.removeEventListener(PRODUCT_CHANGED_EVENT, load);
      window.removeEventListener('depo:credentials-changed', load);
      window.removeEventListener('depo:credentials-cleared', load);
    };
  }, [load]);

  return (
    <section aria-label="Platform service integrations" className="depo-panel">
      <div className="depo-panel__header"><h3>Service integrations</h3>
        <IxButton variant="tertiary" onClick={load} disabled={state.loading}>{state.loading ? 'Checking integrations…' : 'Refresh integrations'}</IxButton>
      </div>
      <div className="depo-panel__body depo-service-integrations" aria-busy={state.loading}>
      <article className="depo-service-card">
        <h3>OSLC integration</h3>
        <div className="depo-service-card__body">
          <Detail label="Service" value={state.oslc?.status || (state.loading ? 'Checking' : 'Unavailable')} />
          <Detail label="Server" value={state.oslc?.server || '—'} />
          <Detail label="Remote provider" value={state.oslc ? (state.oslc.remote_configured ? 'Configured' : 'Not configured') : '—'} />
        </div>
      </article>
      <article className="depo-service-card">
        <h3>Data Catalog</h3>
        <div className="depo-service-card__body">
          <Detail label="Governed product versions" value={state.catalog?.total ?? state.catalog?.count ?? '—'} />
          <Detail label="Endpoint" value="Catalog service" />
          {!state.loading && state.catalog?.total === 0 && <p>No governed product versions are registered in this catalog.</p>}
          {state.catalog?.warning && <p role="alert">{state.catalog.warning}</p>}
          <a href="#/catalog" className="depo-service-card__link">Open Data Catalog</a>
        </div>
      </article>
      <article className="depo-service-card">
        <h3>Data Products</h3>
        <div className="depo-service-card__body">
          <Detail label="Retained packages" value={state.products?.total ?? state.products?.products?.length ?? '—'} />
          <Detail label="Endpoint" value="Data product service" />
          {!state.loading && state.products?.total === 0 && <p>No packages have been retained. Publish an approved data-product draft to create one.</p>}
          {state.products?.warning && <p role="alert">{state.products.warning}</p>}
          {state.products?.products?.some(item => item.status === 'pending_catalog_registration') && <p>Some retained packages are awaiting catalog registration. Open Data Products to inspect delivery status.</p>}
          <a href="#/data-products" className="depo-service-card__link">Open Data Products</a>
        </div>
      </article>
      {state.error && <div role="status" className="depo-service-integrations__error">{state.error}</div>}
      {!state.loading && state.catalog?.total === 0 && state.products?.total === 0 && <FirstProductGuide />}
      </div>
    </section>
  );
}
