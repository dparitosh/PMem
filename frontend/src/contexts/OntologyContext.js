import React, { createContext, useContext, useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { apiClient } from '../services/apiClient';
import { buildUrl } from '../config';
import logger from '../utils/logger';

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
  const [lastUpdated, setLastUpdated] = useState(null);
  const mountedRef = useRef(false);
  const requestRef = useRef(null);
  const abortRef = useRef(null);

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
    return (Array.isArray(rows) ? rows : []).map((o) => {
      const value = o.ontology_id || o.id || o.prefix || o.value || o.name || o.ontology_prefix || '';
      const prefix = o.prefix || o.ontology_prefix || o.ontology_id || o.id || value;
      return {
        value,
        label: o.ontology_name || o.name || o.label || value || prefix,
        prefix,
        ontology_prefix: prefix,
        ontology_id: o.ontology_id || o.id || prefix,
        type: o.file_type || o.type,
        source: o.source,
        namespace: o.namespace || o.source_namespace || o.target_namespace || '',
        source_namespace: o.source_namespace || o.namespace || '',
        target_namespace: o.target_namespace || o.namespace || '',
        status: o.status || o.availability,
        availability: o.availability || o.status,
        node_count: Number(o.node_count || o.neo4j_nodes_merged || 0),
        relationship_count: Number(o.relationship_count || o.neo4j_relationships_merged || 0),
        graph_available:
          Boolean(o.graph_available) ||
          Number(o.node_count || o.neo4j_nodes_merged || 0) > 0 ||
          Number(o.relationship_count || o.neo4j_relationships_merged || 0) > 0 ||
          String(o.status || o.availability || '').toLowerCase() === 'uploaded',
        disabled: Boolean(o.disabled),
        raw: o,
      };
    });
  }, []);

  const fetchOntologies = useCallback(async () => {
    if (requestRef.current) return requestRef.current;
    const controller = new AbortController();
    abortRef.current = controller;
    const request = (async () => {
      try {
        if (mountedRef.current) setLoading(true);
        if (mountedRef.current) setError(null);
        // Prefer the native ontology catalog, then retain the ingestion-owned
        // registry as a read-only bridge for already-published ontologies.
        // This prevents existing QIF/AP242 artifacts from disappearing while
        // their catalog migration is completed.
        const endpoints = [
          buildUrl('/api/v1/ontologies'),
          buildUrl('/api/v1/ontology/registered'),
        ];
        let payload = null;
        let lastError = null;
        for (const endpoint of endpoints) {
          try {
            const response = await apiClient.get(endpoint, { signal: controller.signal });
            payload = response?.data || null;
            const rows = payload?.ontologies || payload?.items || payload?.results || payload?.data?.ontologies || payload?.data?.items || [];
            if (Array.isArray(rows) && rows.length) break;
          } catch (err) {
            lastError = err;
          }
        }
        if (!payload) throw lastError || new Error('Failed to load ontologies');
        const ontologyRows =
          payload.ontologies ||
          payload.items ||
          payload.results ||
          payload.data?.ontologies ||
          payload.data?.items ||
          [];
        const ontologyList = normalizeOntologyRows(ontologyRows);
        if (mountedRef.current) {
          setOntologies(ontologyList);
          setLastUpdated(new Date());
        }
        return ontologyList;
      } catch (err) {
        if (err?.name === 'AbortError' || err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') {
          return [];
        }
        const errorMsg = err.response?.data?.detail || err.message || 'Failed to load ontologies';
        if (mountedRef.current) setError(errorMsg);
        logger.error('[OntologyContext] Failed to fetch ontologies:', err);
        return [];
      } finally {
        if (mountedRef.current) setLoading(false);
        requestRef.current = null;
        if (abortRef.current === controller) abortRef.current = null;
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
          retryDelayMs = 30000;
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
    lastUpdated,
    fetchOntologies,
    getOntologyByPrefix,
    getOntologyById,
  }), [ontologies, loading, error, lastUpdated, fetchOntologies, getOntologyByPrefix, getOntologyById]);

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
