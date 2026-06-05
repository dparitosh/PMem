import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import axios from 'axios';
import config from './config';

const SchemaContext = createContext(null);

/**
 * Provides graph schema (node labels, relationship types, display keys)
 * fetched once from the backend and cached in-memory.
 */
export function SchemaProvider({ children }) {
  const [schema, setSchema] = useState(null);
  const [schemaLoading, setSchemaLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    const shouldRetry = (err) => {
      const code = String(err?.code || '').toUpperCase();
      const msg = String(err?.message || '').toLowerCase();
      return (
        code === 'ERR_NETWORK' ||
        code === 'ECONNABORTED' ||
        msg.includes('timeout') ||
        msg.includes('connection refused') ||
        msg.includes('connection reset')
      );
    };

    const fetchSchema = async () => {
      const maxAttempts = 3;
      try {
        for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
          try {
            const res = await axios.get(`${config.apiUrl}/schema`, { timeout: 20000 });
            if (!cancelled) setSchema(res.data);
            return;
          } catch (err) {
            if (attempt >= maxAttempts || !shouldRetry(err)) {
              throw err;
            }
            await wait(600 * attempt);
          }
        }
      } catch (err) {
        console.warn('Failed to fetch graph schema:', err.message);
      } finally {
        if (!cancelled) setSchemaLoading(false);
      }
    };
    fetchSchema();
    return () => { cancelled = true; };
  }, []);

  /**
   * Return the best display-name for a node based on its label.
   * Falls back through common property names when schema is unavailable.
   */
  const getDisplayName = useCallback((node) => {
    if (!node) return 'Unknown';
    const props = node.properties || node;
    const label = node.labels?.[0] || node.label;

    // 1. Schema-driven: use the pre-computed displayKey for this label
    if (schema?.displayKeys && label && schema.displayKeys[label]) {
      const key = schema.displayKeys[label];
      if (props[key] != null) return String(props[key]);
    }

    // 2. Heuristic fallback (same order used by the backend heuristic)
    const fallbackKeys = [
      'name', 'Name', 'title', 'Title', 'PartName', 'CADDocumentName',
      'code', 'key', 'abbreviation', 'identifier', 'label',
      'ObjectType', 'project_name', 'milestone_name', 'workproduct_name',
      'jira_project_key', 'milestone_abbreviation',
    ];
    for (const k of fallbackKeys) {
      if (props[k] != null) return String(props[k]);
    }

    // 3. Last resort
    return label || node.elementId?.substring(0, 12) || 'Unknown';
  }, [schema]);

  /**
   * Return display name with version appended if available.
   */
  const getDisplayLabel = useCallback((node) => {
    const name = getDisplayName(node);
    const props = node?.properties || node || {};
    const version = props.external_version || props.version;
    if (version) return `${name} (v${version})`;
    return name;
  }, [getDisplayName]);

  /**
   * Return the list of property keys that exist for a given label,
   * ordered by schema definition. Returns null if schema is unavailable.
   */
  const getPropertiesForLabel = useCallback((label) => {
    if (!schema?.nodeLabels || !label) return null;
    return schema.nodeLabels[label] || null;
  }, [schema]);

  return (
    <SchemaContext.Provider value={{
      schema,
      schemaLoading,
      getDisplayName,
      getDisplayLabel,
      getPropertiesForLabel,
    }}>
      {children}
    </SchemaContext.Provider>
  );
}

export function useSchema() {
  return useContext(SchemaContext);
}
