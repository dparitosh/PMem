import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { API_METHODS } from '../services/apiClient';
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

  /**
   * Fetch ontologies from backend
   */
  const fetchOntologies = useCallback(async () => {
    try {
      setError(null);
      const res = await API_METHODS.ontology.listRegistered();
      const ontologyList = (res?.data?.ontologies || []).map(o => ({
        value: o.ontology_id || o.id || o.prefix || o.value || o.name,
        label: o.ontology_name || o.name || o.label || o.ontology_id || o.prefix || o.id,
        prefix: o.prefix || o.ontology_prefix || o.ontology_id || o.id,
        ontology_prefix: o.ontology_prefix || o.prefix || o.ontology_id || o.id,
        ontology_id: o.ontology_id || o.id || o.prefix,
        type: o.file_type || o.type,
        source: o.source,
        namespace: o.namespace || o.source_namespace || o.target_namespace || '',
        source_namespace: o.source_namespace || o.namespace || '',
        target_namespace: o.target_namespace || o.namespace || '',
        status: o.status || o.availability,
        availability: o.availability || o.status,
        node_count: Number(o.node_count || o.neo4j_nodes_merged || 0),
        relationship_count: Number(o.relationship_count || o.neo4j_relationships_merged || 0),
        disabled: o.disabled || ((Number(o.node_count || o.neo4j_nodes_merged || 0)) === 0),
        raw: o, // Keep full metadata
      }));
      setOntologies(ontologyList);
      setLastUpdated(new Date());
      return ontologyList;
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to load ontologies';
      setError(errorMsg);
      logger.error('[OntologyContext] Failed to fetch ontologies:', err);
      return [];
    }
  }, []);

  /**
   * Initial fetch on mount
   */
  useEffect(() => {
    setLoading(true);
    fetchOntologies().finally(() => setLoading(false));
  }, [fetchOntologies]);

  /**
   * Auto-refresh every 30 seconds (single polling, shared across all components)
   */
  useEffect(() => {
    const interval = setInterval(() => {
      fetchOntologies();
    }, 30000); // 30 seconds
    return () => clearInterval(interval);
  }, [fetchOntologies]);

  const value = {
    ontologies,
    loading,
    error,
    lastUpdated,
    fetchOntologies, // Allow manual refresh from components
    getOntologyByPrefix: (prefix) => ontologies.find(o => o.prefix === prefix || o.ontology_prefix === prefix),
    getOntologyById: (id) => ontologies.find(o => o.ontology_id === id || o.value === id),
  };

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
