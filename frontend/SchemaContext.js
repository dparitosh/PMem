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
    const fetchSchema = async () => {
      try {
        const res = await axios.get(`${config.apiUrl}/schema`, { timeout: 10000 });
        if (!cancelled) setSchema(res.data);
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
