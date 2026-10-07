import React, { createContext, useContext, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { apiClient } from '../services/apiClient';
import { buildUrl } from '../config';
import logger from '../utils/logger';
import { normalizeOntologyRows as normalizeRegistryRows, mergeOntologyMetadata } from '../utils/ontologyRegistry';
import { apiErrorMessage } from '../utils/apiErrorMessage';

/**
 * Centralized Ontology Context
 * Single source of truth for registered ontologies across all components
 * Eliminates duplicate API calls and polling from multiple components
 */
const OntologyContext = createContext();

export const OntologyProvider = ({ children }) => {
  const [ontologies, setOntologies] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [warning, setWarning] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);
  const mountedRef = useRef(false);
  const requestRef = useRef(null);
  const abortRef = useRef(null);
  const registryFailureRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  /**
   * Fetch ontologies from backend
   */
  const normalizeOntologyRows = useCallback((rows = []) => {
    return normalizeRegistryRows(rows);
  }, []);

  const fetchOntologies = useCallback(async (force = false) => {
    if (requestRef.current && !force) return requestRef.current;
    if (force) abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const request = (async () => {
      try {
        if (mountedRef.current) setLoading(true);
        if (mountedRef.current) setError(null);
        if (mountedRef.current) setWarning('');
        // Prefer the native ontology catalog, then retain the ingestion-owned
        // registry as a read-only bridge for already-published ontologies.
        // This prevents existing QIF/AP242 artifacts from disappearing while
        // their catalog migration is completed.
        const paths = ['/api/v1/ontologies', '/api/v1/ontology/registered'];
        const results = await Promise.allSettled(paths.map(path => Promise.resolve().then(() =>
          apiClient.get(buildUrl(path), { signal: controller.signal, timeout: 15000 }))));
        const merged = new Map();
        let successes = 0;
        let lastError = null;
        const failedSources = [];
        for (const [index, result] of results.entries()) {
          if (controller.signal.aborted) return [];
          if (result.status === 'rejected') { lastError = result.reason; failedSources.push(`${index === 0 ? 'Ontology catalog' : 'Ingestion registry'} (${apiErrorMessage(result.reason, 'request failed')})`); continue; }
          const payload = result.value?.data || {};
          const rows = payload.ontologies || payload.items || payload.results || payload.data?.ontologies || payload.data?.items;
          if (!Array.isArray(rows)) { lastError = new Error('Registry returned an invalid ontology list.'); failedSources.push(index === 0 ? 'Ontology catalog' : 'Ingestion registry'); continue; }
          successes += 1;
          for (const row of normalizeOntologyRows(rows)) {
            if (!row.value) continue;
            if (!merged.has(row.value)) merged.set(row.value, row);
            else {
              const existing = merged.get(row.value);
              // Native identities remain authoritative; legacy metadata can fill gaps.
              merged.set(row.value, mergeOntologyMetadata(existing, row));
            }
          }
        }
        if (!successes) throw lastError || new Error('Failed to load ontologies');
        if (controller.signal.aborted) return [];
        const ontologyList = [...merged.values()];
        if (mountedRef.current) {
          registryFailureRef.current = failedSources.length > 0;
          setOntologies(ontologyList);
          setWarning(failedSources.length ? `Partial ontology list: ${failedSources.join(', ')} could not be loaded. Other registry results are shown; retry to verify completeness.` : '');
          setLastUpdated(new Date());
        }
        return ontologyList;
      } catch (err) {
        if (err?.name === 'AbortError' || err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') {
          return [];
        }
        const errorMsg = apiErrorMessage(err, 'Failed to load ontology registries.');
        registryFailureRef.current = true;
        if (mountedRef.current) setError(errorMsg);
        logger.error('[OntologyContext] Failed to fetch ontologies:', err);
        return [];
      } finally {
        if (mountedRef.current && abortRef.current === controller) setLoading(false);
        if (abortRef.current === controller) {
          requestRef.current = null;
          abortRef.current = null;
        }
      }
    })();
    requestRef.current = request;
    return request;
  }, [normalizeOntologyRows]);

  /**
   * Initial fetch on mount
   */
  useEffect(() => {
    fetchOntologies();
    const refresh = () => { setOntologies([]); fetchOntologies(true); };
    const changed = () => fetchOntologies(true);
    window.addEventListener('depo:credentials-changed', refresh);
    window.addEventListener('depo:credentials-cleared', refresh);
    window.addEventListener('depo:ontologies-changed', changed);
    return () => {
      window.removeEventListener('depo:credentials-changed', refresh);
      window.removeEventListener('depo:credentials-cleared', refresh);
      window.removeEventListener('depo:ontologies-changed', changed);
    };
  }, [fetchOntologies]);

  /**
   * Auto-refresh every 30 seconds (single polling, shared across all components)
   */
  useEffect(() => {
    let active = true;
    let retryDelayMs = 30000;
    let retryTimer = null;
    const scheduleNextFetch = () => {
      if (!active) return;
      retryTimer = setTimeout(async () => {
        if (typeof document !== 'undefined' && document.hidden) {
          scheduleNextFetch();
          return;
        }
        try {
          await fetchOntologies();
          retryDelayMs = registryFailureRef.current ? Math.min(retryDelayMs * 2, 300000) : 30000;
        } catch (_error) {
          retryDelayMs = Math.min(retryDelayMs * 2, 300000);
        } finally {
          scheduleNextFetch();
        }
      }, retryDelayMs);
    };
    scheduleNextFetch();
    return () => {
      active = false;
      if (retryTimer) clearTimeout(retryTimer);
    };
  }, [fetchOntologies]);

  const getOntologyByPrefix = useCallback(
    (prefix) => ontologies.find(o => o.prefix === prefix || o.ontology_prefix === prefix),
    [ontologies],
  );
  const getOntologyById = useCallback(
    (id) => ontologies.find(o => o.ontology_id === id || o.value === id),
    [ontologies],
  );
  const value = useMemo(() => ({
    ontologies,
    loading,
    error,
    warning,
    lastUpdated,
    fetchOntologies,
    getOntologyByPrefix,
    getOntologyById,
  }), [ontologies, loading, error, warning, lastUpdated, fetchOntologies, getOntologyByPrefix, getOntologyById]);

  return (
    <OntologyContext.Provider value={value}>
      {children}
    </OntologyContext.Provider>
  );
};

/**
 * Hook to use Ontology Context
 * Usage: const { ontologies, loading, error, fetchOntologies } = useOntologies();
 */
export const useOntologies = () => {
  const context = useContext(OntologyContext);
  if (!context) {
    throw new Error('useOntologies must be used within OntologyProvider');
  }
  return context;
};
