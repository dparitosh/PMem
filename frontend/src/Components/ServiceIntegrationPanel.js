import React, { useCallback, useEffect, useRef, useState } from 'react';
import { IxButton } from '@siemens/ix-react';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import FirstProductGuide from './FirstProductGuide';
import { readProductCollection, PRODUCT_REFRESH_MS, PRODUCT_CHANGED_EVENT } from '../services/productService';

const serviceUrl = (service, path) => buildSemanticServiceUrl(service, path);

function collectionRequest(service, signal) {
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
  const [state, setState] = useState({ oslc: { loading: true }, catalog: { loading: true }, products: { loading: true } });
  const loading = Object.values(state).some(item => item.loading);

  const requestRef = useRef(null);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setState({ oslc: { loading: true }, catalog: { loading: true }, products: { loading: true } });
    const requests = {
      oslc: () => apiClient.get(serviceUrl('oslc', '/api/v1/oslc/health'), { signal: controller.signal, timeout: 15000 }),
      catalog: () => collectionRequest('catalog', controller.signal),
      products: () => collectionRequest('dataProducts', controller.signal),
    };
    await Promise.all(Object.entries(requests).map(async ([key, request]) => {
      try {
        const { data } = await request();
        if (controller.signal.aborted || requestRef.current !== controller) return;
        setState(previous => ({ ...previous, [key]: { ...data, loading: false } }));
      } catch (error) {
        if (controller.signal.aborted || requestRef.current !== controller) return;
        const detail = error.response?.data?.detail || error.message;
        const message = typeof detail === 'string' ? detail : 'Unable to check this service. Retry or inspect service logs.';
        setState(previous => ({ ...previous, [key]: { loading: false, error: message } }));
      }
    }));
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
        <IxButton variant="tertiary" onClick={load} disabled={loading}>{loading ? 'Checking integrations…' : 'Refresh integrations'}</IxButton>
      </div>
      <div className="depo-panel__body depo-service-integrations">
      <article className="depo-service-card" aria-busy={state.oslc.loading}>
        <h3>OSLC integration</h3>
        <div className="depo-service-card__body">
          <Detail label="Service" value={state.oslc?.status || (state.oslc.loading ? 'Checking' : 'Unavailable')} />
          <Detail label="Server" value={state.oslc?.server || '—'} />
          <Detail label="Remote provider" value={state.oslc.loading || state.oslc.error ? "Unavailable" : (state.oslc.remote_configured ? "Address saved" : "Not configured")} />
          {state.oslc.remote_configured && <p>Remote address is saved. Connection and access have not been verified by this check.</p>}
          {state.oslc.error && <p role="status">OSLC: {state.oslc.error}</p>}
        </div>
      </article>
      <article className="depo-service-card" aria-busy={state.catalog.loading}>
        <h3>Data Catalog</h3>
        <div className="depo-service-card__body">
          <Detail label="Registered product versions" value={state.catalog?.total ?? state.catalog?.count ?? '—'} />
          <p>Counts catalog registrations, not imported sources or available analytics.</p>
          {!state.catalog.loading && state.catalog?.total === 0 && <p>No product versions are registered yet. Imported sources and analytics may still be available.</p>}
          {state.catalog?.warning && <p role="alert">{state.catalog.warning}</p>}
          {state.catalog.error && <p role="status">{state.catalog.error}</p>}
        </div>
        <a href="#/catalog" className="depo-service-card__link">Open Data Catalog</a>
      </article>
      <article className="depo-service-card" aria-busy={state.products.loading}>
        <h3>Data Products</h3>
        <div className="depo-service-card__body">
          <Detail label="Product package records" value={state.products?.total ?? state.products?.products?.length ?? '—'} />
          <p>Counts retained package records, not datasets or analytics tables. Check lifecycle and delivery status in Data Products.</p>
          {!state.products.loading && state.products?.total === 0 && <p>No product packages are recorded yet. Review available analytics or completed processing results to prepare a product.</p>}
          {state.products?.warning && <p role="alert">{state.products.warning}</p>}
          {state.products?.products?.some(item => item.status === 'pending_catalog_registration') && <p>Some retained packages are awaiting catalog registration. Open Data Products to inspect delivery status.</p>}
          {state.products.error && <p role="status">{state.products.error}</p>}
        </div>
        <a href="#/data-products" className="depo-service-card__link">Open Data Products</a>
      </article>
      {!state.catalog.loading && state.catalog?.total === 0 && state.products?.total === 0 && <FirstProductGuide />}
      </div>
    </section>
  );
}
