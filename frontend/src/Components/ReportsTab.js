import React, { useEffect, useMemo, useState } from 'react';
import { API, buildUrl } from '../config';
import { apiClient } from '../services/apiClient';
import { normalizeGraphDataset as normalizeGraphDatasetShared } from '../utils/graphUtils';
import { useOntologies } from '../contexts/OntologyContext';

const NOISY_COLUMNS = new Set([
  'args',
  'ref_ids',
  'import_row_key',
  'source_line',
  'raw_line',
  'properties',
  'x',
  'y',
  'vx',
  'vy',
  'index',
  'elementId',
  'elementID',
  'X',
  'Y',
  'VX',
  'VY',
]);

const PRIORITY_COLUMNS = [
  'entity_type',
  'name',
  'title',
  'type',
  'id',
  'part_name',
  'partnumber',
  'source',
  'target',
  'relationship_type',
  'import_id',
  'source_tag',
  'ref_type',
];

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];
const RELATIONSHIP_PAGE_SIZE = 25;
const RELATIONSHIP_EXPORT_HEADERS = ['relationship_type', 'source', 'target', 'count'];
const DEFAULT_VISIBLE_COLUMNS = [
  'entity_type',
  'name',
  'title',
  'type',
  'id',
  'part_name',
  'source_tag',
  'ref_type',
];
const REPORT_PRESETS = {
  overview: ['entity_type', 'name', 'title', 'type', 'id', 'source_tag'],
  governance: ['entity_type', 'name', 'type', 'source_tag', 'ref_type', 'id'],
  lineage: ['name', 'id', 'import_id', 'source_tag', 'ref_type', 'title'],
};

const stripUnwanted = (rows) =>
  rows.map((row) => {
    const next = { ...row };
    NOISY_COLUMNS.forEach((key) => delete next[key]);
    return next;
  });

const formatCellValue = (value) => {
  if (value == null) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
};

const formatHeaderLabel = (header) => {
  const labels = {
    entity_type: 'Entity',
    source_tag: 'Source',
    ref_type: 'Reference Type',
    partnumber: 'Part Number',
    relationship_type: 'Relationship Type',
  };
  return labels[header] || header.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase());
};

const buildPresetVisibility = (headers, presetId) => {
  const preferred = REPORT_PRESETS[presetId] || DEFAULT_VISIBLE_COLUMNS;
  const preferredSet = new Set(preferred);
  const visible = {};
  headers.forEach((header) => {
    visible[header] = preferredSet.has(header);
  });
  if (!Object.values(visible).some(Boolean)) {
    headers.slice(0, 6).forEach((header) => {
      visible[header] = true;
    });
  }
  return visible;
};

const escapeCsv = (value) => JSON.stringify(value == null ? '' : String(value));

const downloadCsv = (filename, headers, rows) => {
  const csv = [
    headers.join(','),
    ...rows.map((row) => headers.map((header) => escapeCsv(row[header])).join(',')),
  ].join('\n');

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
};

const normalizeReportNode = (item = {}) => {
  const node = item?.n || item?.node || item;
  const props = node?.properties || item?.properties || {};
  const labels = node?.labels || item?.node_labels || item?.labels || [];
  const type = Array.isArray(labels) ? labels.join(', ') : String(labels || item?.type || node?.label || '');
  return {
    elementId: node?.elementId || node?.element_id || node?.id || item?.elementId || item?.element_id,
    type,
    ...props,
    ...Object.fromEntries(Object.entries(item || {}).filter(([key]) => !['n', 'node', 'properties', 'labels', 'node_labels'].includes(key))),
    name: props.name || node?.name || item?.name || props.label || node?.label || item?.label,
    label: props.label || node?.label || item?.label,
  };
};

const processSearchResults = (results) => {
  if (!Array.isArray(results)) return [];
  return stripUnwanted(results.map(normalizeReportNode));
};

const getHeaders = (rows) => {
  if (!rows.length) return [];

  const headerSet = new Set();
  rows.forEach((row) => {
    Object.keys(row || {}).forEach((key) => {
      if (!NOISY_COLUMNS.has(key)) {
        headerSet.add(key);
      }
    });
  });

  const headers = Array.from(headerSet);
  headers.sort((left, right) => {
    const leftPriority = PRIORITY_COLUMNS.indexOf(left);
    const rightPriority = PRIORITY_COLUMNS.indexOf(right);

    if (leftPriority !== -1 || rightPriority !== -1) {
      if (leftPriority === -1) return 1;
      if (rightPriority === -1) return -1;
      return leftPriority - rightPriority;
    }

    return left.localeCompare(right);
  });

  return headers;
};

const discoverTypes = (rows) => {
  const types = new Map();
  rows.forEach((row) => {
    const firstType = getPrimaryType(row);
    if (!firstType) return;
    types.set(firstType, (types.get(firstType) || 0) + 1);
  });
  return Array.from(types.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([type, count]) => ({ type, count }));
};

const getPrimaryType = (row) => {
  if (!row) return '';

  const rawType = row.type;
  if (Array.isArray(rawType)) {
    const first = rawType.map((value) => String(value || '').trim()).find(Boolean);
    if (first) return first;
  }
  if (typeof rawType === 'string') {
    const first = rawType
      .split(',')
      .map((value) => value.trim())
      .find(Boolean);
    if (first) return first;
  }
  if (typeof rawType === 'number' || typeof rawType === 'boolean') {
    return String(rawType);
  }

  const label = row.label;
  if (Array.isArray(label)) {
    const first = label.map((value) => String(value || '').trim()).find(Boolean);
    if (first) return first;
  }
  if (typeof label === 'string' && label.trim()) return label.trim();

  const fallback = row.entity_type || row.node_type || row.class_name || row.ontology_class || row.name;
  return fallback == null ? '' : String(fallback).trim();
};

const buildRelationshipRows = (graphData) => {
  const links = graphData?.links || graphData?.edges || [];
  const nodes = graphData?.nodes || [];
  if (!links.length) return [];

  const nodeMap = new Map();
  nodes.forEach((node) => {
    const id = node.elementId || node.id;
    if (id) {
      nodeMap.set(String(id), node.name || node.label || node.uri || String(id));
    }
  });

  const resolveNodeName = (ref) => {
    if (!ref) return '';
    if (typeof ref === 'object') {
      const id = ref.elementId || ref.id;
      return nodeMap.get(String(id)) || ref.name || ref.label || String(id);
    }
    return nodeMap.get(String(ref)) || String(ref);
  };

  const rows = new Map();
  links.forEach((link) => {
    const relationshipType = link.type || link.label || 'RELATED';
    const source = resolveNodeName(link.source);
    const target = resolveNodeName(link.target);
    const key = `${relationshipType}||${source}||${target}`;

    if (!rows.has(key)) {
      rows.set(key, { relationship_type: relationshipType, source, target, count: 1 });
    } else {
      rows.get(key).count += 1;
    }
  });

  return Array.from(rows.values()).sort(
    (a, b) =>
      a.relationship_type.localeCompare(b.relationship_type) ||
      a.source.localeCompare(b.source) ||
      a.target.localeCompare(b.target)
  );
};

const getDistinctValues = (rows, key) => {
  const values = new Set();
  rows.forEach((row) => {
    if (row[key] !== undefined && row[key] !== null && row[key] !== '') {
      values.add(String(row[key]));
    }
  });
  return Array.from(values).sort();
};

const pageSlice = (rows, page, pageSize) => {
  const start = (page - 1) * pageSize;
  return rows.slice(start, start + pageSize);
};

const buildNodeReportRows = (graphData, searchResults) => {
  const fromSearch = processSearchResults(searchResults);
  if (fromSearch.length > 0) return fromSearch;

  const graphNodes = graphData?.nodes || [];
  const rows = stripUnwanted(
    graphNodes.map((node) => ({
      elementId: node.elementId || node.id,
      type: Array.isArray(node.labels) ? node.labels.join(', ') : (node.label || ''),
      ...(node.properties || {}),
      name: node.name || node.properties?.name || node.label || node.properties?.label,
      label: node.label || node.properties?.label,
    }))
  );

  const ontologyTypes = new Set(['OntologyClass', 'ObjectProperty', 'DatatypeProperty']);
  const businessRows = rows.filter((row) => {
    const primaryType = getPrimaryType(row);
    const name = String(row.name || row.title || row.code || row.id || '').trim();
    if (ontologyTypes.has(primaryType)) return false;
    if (!name) return false;
    return !/^id[\w:-]*$/i.test(name);
  });

  return businessRows.length > 0 ? businessRows : rows;
};

const ReportsTab = ({ searchResults, graphData }) => {
  const { ontologies } = useOntologies();
  const [activeReport, setActiveReport] = useState('search');
  const [filters, setFilters] = useState({});
  const [sortColumn, setSortColumn] = useState('');
  const [sortDirection, setSortDirection] = useState('asc');
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(25);
  const [visibleColumns, setVisibleColumns] = useState({});
  const [showColumnSelector, setShowColumnSelector] = useState(false);
  const [reportPreset, setReportPreset] = useState('overview');
  const [relTypeFilter, setRelTypeFilter] = useState('');
  const [relSearchTerm, setRelSearchTerm] = useState('');
  const [relPage, setRelPage] = useState(1);
  const [fallbackGraphData, setFallbackGraphData] = useState({ nodes: [], links: [] });
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState('');

  const effectiveGraphData = useMemo(() => {
    const hasPrimaryGraph = (graphData?.nodes || []).length > 0 || (graphData?.links || []).length > 0;
    return hasPrimaryGraph ? graphData : fallbackGraphData;
  }, [fallbackGraphData, graphData]);

  useEffect(() => {
    const hasPrimaryGraph = (graphData?.nodes || []).length > 0 || (graphData?.links || []).length > 0;
    if (hasPrimaryGraph || (fallbackGraphData.nodes || []).length > 0) return undefined;

    let cancelled = false;
    const loadGraph = async () => {
      setGraphLoading(true);
      setGraphError('');
      try {
        const response = await apiClient.get(buildUrl(API.graph.graphView), { params: { limit: 5000 } });
        const normalized = normalizeGraphDatasetShared(response.data);
        if (!cancelled) setFallbackGraphData(normalized);
      } catch (error) {
        if (!cancelled) setGraphError(error?.response?.data?.detail || error.message || 'Failed to load graph data for reports.');
      } finally {
        if (!cancelled) setGraphLoading(false);
      }
    };

    loadGraph();
    return () => { cancelled = true; };
  }, [fallbackGraphData.nodes, graphData]);

  const ontologyRows = useMemo(() => (ontologies || []).map((ontology) => ({
    ontology: ontology.label || ontology.ontology_id || ontology.prefix,
    prefix: ontology.prefix || ontology.ontology_prefix || '',
    ontology_id: ontology.ontology_id || ontology.value || '',
    status: ontology.status || '',
    availability: ontology.graph_available === false ? 'registered only' : (ontology.availability || 'available'),
    type: ontology.type || '',
    namespace: ontology.namespace || ontology.target_namespace || ontology.source_namespace || '',
    nodes: ontology.node_count || 0,
    relationships: ontology.relationship_count || 0,
  })), [ontologies]);

  const processedResults = useMemo(() => buildNodeReportRows(effectiveGraphData, searchResults), [effectiveGraphData, searchResults]);
  const baseNodeHeaders = useMemo(() => getHeaders(processedResults), [processedResults]);
  const availableTypes = useMemo(() => discoverTypes(processedResults), [processedResults]);
  const relationshipRows = useMemo(() => buildRelationshipRows(effectiveGraphData), [effectiveGraphData]);

  const relTypesSummary = useMemo(() => {
    const counts = new Map();
    relationshipRows.forEach((row) => {
      counts.set(row.relationship_type, (counts.get(row.relationship_type) || 0) + row.count);
    });
    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([type, count]) => ({ type, count }));
  }, [relationshipRows]);

  const nodeRows = useMemo(() => {
    if (activeReport === 'ontologies') return ontologyRows;
    if (activeReport === 'search') return processedResults;
    return processedResults.filter((row) => getPrimaryType(row) === activeReport);
  }, [activeReport, ontologyRows, processedResults]);

  const relationshipScopeLabel = useMemo(() => {
    const searchCount = Array.isArray(searchResults) ? searchResults.length : 0;
    if (searchCount > 0) {
      return `Relationship rows are derived from the current graph canvas while node rows are filtered to ${searchCount} selected search result(s).`;
    }
    const graphNodeCount = (effectiveGraphData?.nodes || []).length;
    return graphNodeCount > 0
      ? `Relationship rows are derived from the current graph canvas (${graphNodeCount} visible node(s)).`
      : 'Relationship rows are derived from the current graph canvas.';
  }, [effectiveGraphData, searchResults]);

  const filterableHeaders = useMemo(() => {
    const headers = getHeaders(nodeRows);
    return headers.filter((header) => {
      if (NOISY_COLUMNS.has(header)) return false;
      const values = getDistinctValues(nodeRows, header);
      if (values.length <= 1 || values.length > 20) return false;
      const avgLength =
        values.reduce((sum, value) => sum + value.length, 0) / Math.max(values.length, 1);
      return avgLength <= 40;
    }).slice(0, 4);
  }, [nodeRows]);

  const filteredNodeRows = useMemo(() => {
    const filtered = nodeRows.filter((row) =>
      Object.entries(filters).every(([key, value]) => !value || String(row[key]) === value)
    );

    if (!sortColumn) return filtered;

    const direction = sortDirection === 'asc' ? 1 : -1;
    return [...filtered].sort((left, right) => {
      const leftValue = formatCellValue(left[sortColumn]).toLowerCase();
      const rightValue = formatCellValue(right[sortColumn]).toLowerCase();
      if (leftValue === rightValue) return 0;
      return leftValue > rightValue ? direction : -direction;
    });
  }, [filters, nodeRows, sortColumn, sortDirection]);

  const nodeHeaders = useMemo(() => getHeaders(filteredNodeRows), [filteredNodeRows]);
  const visibleHeaders = useMemo(
    () => nodeHeaders.filter((header) => visibleColumns[header] !== false),
    [nodeHeaders, visibleColumns]
  );

  const pagedNodeRows = useMemo(
    () => pageSlice(filteredNodeRows, currentPage, itemsPerPage),
    [filteredNodeRows, currentPage, itemsPerPage]
  );

  const filteredRelationshipRows = useMemo(() => {
    let rows = relationshipRows;

    if (relTypeFilter) {
      rows = rows.filter((row) => row.relationship_type === relTypeFilter);
    }

    if (relSearchTerm) {
      const query = relSearchTerm.toLowerCase();
      rows = rows.filter(
        (row) =>
          row.relationship_type.toLowerCase().includes(query) ||
          row.source.toLowerCase().includes(query) ||
          row.target.toLowerCase().includes(query)
      );
    }

    return rows;
  }, [relationshipRows, relSearchTerm, relTypeFilter]);

  const pagedRelationshipRows = useMemo(
    () => pageSlice(filteredRelationshipRows, relPage, RELATIONSHIP_PAGE_SIZE),
    [filteredRelationshipRows, relPage]
  );

  const totalNodePages = Math.max(1, Math.ceil(filteredNodeRows.length / itemsPerPage));
  const totalRelationshipPages = Math.max(
    1,
    Math.ceil(filteredRelationshipRows.length / RELATIONSHIP_PAGE_SIZE)
  );

  useEffect(() => {
    setCurrentPage(1);
  }, [activeReport, itemsPerPage]);

  useEffect(() => {
    setCurrentPage((page) => Math.min(Math.max(page, 1), totalNodePages));
  }, [totalNodePages]);

  useEffect(() => {
    setRelPage((page) => Math.min(Math.max(page, 1), totalRelationshipPages));
  }, [totalRelationshipPages]);

  useEffect(() => {
    setVisibleColumns((previous) => {
      const headers = baseNodeHeaders.length ? baseNodeHeaders : getHeaders(nodeRows);
      if (!headers.length) return previous;

      const next = { ...previous };
      headers.forEach((header) => {
        if (!Object.prototype.hasOwnProperty.call(next, header)) {
          next[header] = DEFAULT_VISIBLE_COLUMNS.includes(header);
        }
      });
      return next;
    });
  }, [baseNodeHeaders, nodeRows]);

  const clearFilters = () => setFilters({});

  const applyReportPreset = (presetId) => {
    setReportPreset(presetId);
    setFilters({});
    setShowColumnSelector(false);
    if (presetId === 'traceability') {
      setActiveReport('relationships');
      return;
    }
    if (presetId === 'governance') {
      setActiveReport('ontologies');
      setVisibleColumns({});
      return;
    }
    setActiveReport('search');
    setVisibleColumns(buildPresetVisibility(baseNodeHeaders, presetId));
  };

  const handleFilterChange = (header, value) => {
    setFilters((previous) => {
      const next = { ...previous };
      if (!value) {
        delete next[header];
      } else {
        next[header] = value;
      }
      return next;
    });
  };

  const handleSort = (header) => {
    if (activeReport !== 'search') return;
    setSortDirection((previous) =>
      sortColumn === header && previous === 'asc' ? 'desc' : 'asc'
    );
    setSortColumn(header);
  };

  const toggleColumn = (header) => {
    setVisibleColumns((previous) => ({
      ...previous,
      [header]: previous[header] === false,
    }));
  };

  const setAllColumnsVisible = (visible) => {
    setVisibleColumns((previous) => {
      const next = { ...previous };
      nodeHeaders.forEach((header) => {
        next[header] = visible;
      });
      return next;
    });
  };

  const nodeSummaryLabel =
    activeReport === 'search'
      ? `${filteredNodeRows.length} rows`
      : `${filteredNodeRows.length} items`;

  const nodeStart = filteredNodeRows.length === 0 ? 0 : (currentPage - 1) * itemsPerPage + 1;
  const nodeEnd = Math.min(currentPage * itemsPerPage, filteredNodeRows.length);

  return (
    <div style={{ minHeight: '100%', padding: '8px 0 0' }}>
      <div
        style={{
          display: 'grid',
          gap: 16,
          gridTemplateColumns: 'minmax(0, 1fr)',
        }}
      >
        <section
          style={{
            background: '#ffffff',
            border: '1px solid #d9e2ec',
            borderRadius: 8,
            padding: 16,
          }}
        >
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              gap: 12,
              marginBottom: 14,
            }}
          >
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              <button
                className="btn btn-sm"
                style={{
                  color: activeReport === 'search' ? '#fff' : '#004B87',
                  background: activeReport === 'search' ? '#004B87' : '#eef4fb',
                  border: '1px solid #004B87',
                  fontWeight: 700,
                  fontSize: 13,
                  borderRadius: 999,
                  padding: '6px 12px',
                }}
                onClick={() => {
                  setReportPreset('custom');
                  setActiveReport('search');
                }}
              >
                Nodes
              </button>
              <button
                className="btn btn-sm"
                style={{
                  color: activeReport === 'relationships' ? '#fff' : '#0a8276',
                  background: activeReport === 'relationships' ? '#0a8276' : '#e8f4f3',
                  border: '1px solid #0a8276',
                  fontWeight: 700,
                  fontSize: 13,
                  borderRadius: 999,
                  padding: '6px 12px',
                }}
                onClick={() => {
                  setReportPreset('traceability');
                  setActiveReport('relationships');
                }}
              >
                Links
                {relationshipRows.length > 0 && (
                  <span
                    style={{
                      marginLeft: 6,
                      background: 'rgba(255,255,255,0.24)',
                      borderRadius: 999,
                      padding: '1px 6px',
                      fontSize: 11,
                    }}
                  >
                    {relationshipRows.length}
                  </span>
                )}
              </button>
              <button
                className="btn btn-sm"
                style={{
                  color: activeReport === 'ontologies' ? '#fff' : '#6b4e00',
                  background: activeReport === 'ontologies' ? '#6b4e00' : '#fff8e1',
                  border: '1px solid #c49a00',
                  fontWeight: 700,
                  fontSize: 13,
                  borderRadius: 999,
                  padding: '6px 12px',
                }}
                onClick={() => {
                  setReportPreset('governance');
                  setActiveReport('ontologies');
                }}
              >
                Ontologies
                <span style={{ marginLeft: 6, opacity: 0.8, fontSize: 11 }}>{ontologyRows.length}</span>
              </button>              {availableTypes.map(({ type, count }) => (
                <button
                  key={type}
                  className="btn btn-sm"
                  onClick={() => {
                    setReportPreset('custom');
                    setActiveReport(type);
                  }}
                  style={{
                    color: activeReport === type ? '#fff' : '#33506b',
                    background: activeReport === type ? '#33506b' : '#f3f6f9',
                    border: '1px solid #cbd5e1',
                    fontWeight: 700,
                    fontSize: 13,
                    borderRadius: 999,
                    padding: '6px 12px',
                  }}
                >
                  {type}
                  <span style={{ marginLeft: 6, opacity: 0.8, fontSize: 11 }}>{count}</span>
                </button>
              ))}
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
                {[
                  { id: 'overview', label: 'Overview' },
                  { id: 'governance', label: 'Governance' },
                  { id: 'lineage', label: 'Lineage' },
                  { id: 'traceability', label: 'Traceability' },
                ].map((preset) => (
                  <button
                    key={preset.id}
                    className="btn btn-sm"
                    onClick={() => applyReportPreset(preset.id)}
                    style={{
                      color: reportPreset === preset.id ? '#fff' : '#52606d',
                      background: reportPreset === preset.id ? '#33506b' : '#f8fafc',
                      border: '1px solid #cbd5e1',
                      fontWeight: 700,
                      fontSize: 12,
                      borderRadius: 999,
                      padding: '5px 10px',
                    }}
                  >
                    {preset.label}
                  </button>
                ))}
              </div>
              {activeReport !== 'relationships' && filteredNodeRows.length > 0 && (
                <button
                  className="btn btn-sm"
                  onClick={() =>
                    downloadCsv(
                      `${activeReport}_all_${new Date().toISOString().split('T')[0]}.csv`,
                      visibleHeaders,
                      filteredNodeRows
                    )
                  }
                  style={{
                    color: '#004B87',
                    background: '#e8f4fd',
                    border: '1px solid #004B87',
                    fontWeight: 700,
                    fontSize: 12,
                  }}
                >
                  Export CSV
                </button>
              )}
              {activeReport === 'relationships' && filteredRelationshipRows.length > 0 && (
                <button
                  className="btn btn-sm"
                  onClick={() =>
                    downloadCsv(
                      `relationships_${relTypeFilter || 'all'}_${new Date().toISOString().split('T')[0]}.csv`,
                      RELATIONSHIP_EXPORT_HEADERS,
                      filteredRelationshipRows.map((row) => ({
                        relationship_type: row.relationship_type,
                        source: row.source,
                        target: row.target,
                        count: row.count,
                      }))
                    )
                  }
                  style={{
                    color: '#0a8276',
                    background: '#e8f4f3',
                    border: '1px solid #0a8276',
                    fontWeight: 700,
                    fontSize: 12,
                  }}
                >
                  Export CSV
                </button>
              )}
              <div style={{ fontSize: 12, color: '#52606d', fontWeight: 700 }}>
                {activeReport === 'relationships'
                  ? `${filteredRelationshipRows.length} relationship rows`
                  : nodeSummaryLabel}
              </div>
            </div>
          </div>

          {(graphLoading || graphError) && (
            <div
              style={{
                marginBottom: 12,
                padding: '10px 12px',
                borderRadius: 8,
                border: `1px solid ${graphError ? '#fecaca' : '#d9e2ec'}`,
                background: graphError ? '#fef2f2' : '#f8fafc',
                color: graphError ? '#991b1b' : '#52606d',
                fontSize: 12,
                fontWeight: 600,
              }}
            >
              {graphLoading ? 'Loading graph data for reports...' : graphError}
            </div>
          )}

          {activeReport === 'relationships' ? (
            <>
              <div style={{ fontSize: 12, color: '#52606d', marginBottom: 12 }}>
                {relationshipScopeLabel}
              </div>

              {relTypesSummary.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
                  {relTypesSummary.map(({ type, count }) => (
                    <button
                      key={type}
                      onClick={() => setRelTypeFilter(relTypeFilter === type ? '' : type)}
                      style={{
                        padding: '4px 10px',
                        borderRadius: 999,
                        fontSize: 12,
                        fontWeight: 700,
                        cursor: 'pointer',
                        background: relTypeFilter === type ? '#0a8276' : '#ffffff',
                        color: relTypeFilter === type ? '#ffffff' : '#0a8276',
                        border: '1px solid #0a8276',
                      }}
                    >
                      {type} <span style={{ opacity: 0.8 }}>({count})</span>
                    </button>
                  ))}
                </div>
              )}

              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 10,
                  alignItems: 'center',
                  marginBottom: 12,
                }}
              >
                <input
                  type="text"
                  placeholder="Search relationship rows..."
                  value={relSearchTerm}
                  onChange={(event) => setRelSearchTerm(event.target.value)}
                  style={{
                    flex: '1 1 280px',
                    padding: '8px 10px',
                    borderRadius: 6,
                    border: '1px solid #cbd5e1',
                    fontSize: 13,
                  }}
                />
                {relTypeFilter && (
                  <button
                    className="btn btn-sm"
                    onClick={() => setRelTypeFilter('')}
                    style={{
                      color: '#8a5a00',
                      background: '#fff8e1',
                      border: '1px solid #ffe082',
                      fontWeight: 700,
                      fontSize: 12,
                    }}
                  >
                    Clear Type Filter
                  </button>
                )}
              </div>

              <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
                {pagedRelationshipRows.length === 0 ? (
                  <div style={{ padding: 24, color: '#7b8794', textAlign: 'center' }}>
                    {relationshipRows.length === 0
                      ? 'No graph relationships are available yet.'
                      : 'No relationships match the current filter.'}
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table className="table table-striped table-hover mb-0">
                      <thead className="sticky-top bg-light">
                        <tr>
                          <th style={{ minWidth: 180, borderBottom: '2px solid #0a8276' }}>
                            RELATIONSHIP TYPE
                          </th>
                          <th style={{ minWidth: 220, borderBottom: '2px solid #0a8276' }}>SOURCE</th>
                          <th style={{ minWidth: 220, borderBottom: '2px solid #0a8276' }}>TARGET</th>
                          <th style={{ minWidth: 90, textAlign: 'right', borderBottom: '2px solid #0a8276' }}>
                            COUNT
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {pagedRelationshipRows.map((row, index) => (
                          <tr key={`${row.relationship_type}-${row.source}-${row.target}-${index}`}>
                            <td>
                              <span
                                style={{
                                  background: '#e8f4f3',
                                  color: '#0a5952',
                                  padding: '3px 9px',
                                  borderRadius: 999,
                                  fontSize: 12,
                                  fontWeight: 700,
                                }}
                              >
                                {row.relationship_type}
                              </span>
                            </td>
                            <td title={row.source}>{row.source}</td>
                            <td title={row.target}>{row.target}</td>
                            <td style={{ textAlign: 'right', color: '#52606d' }}>{row.count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {filteredRelationshipRows.length > 0 && (
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 12,
                    marginTop: 12,
                    flexWrap: 'wrap',
                  }}
                >
                  <div style={{ fontSize: 12, color: '#52606d' }}>
                    Showing {(relPage - 1) * RELATIONSHIP_PAGE_SIZE + 1} to{' '}
                    {Math.min(relPage * RELATIONSHIP_PAGE_SIZE, filteredRelationshipRows.length)} of{' '}
                    {filteredRelationshipRows.length}
                  </div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button
                      className="btn btn-sm"
                      onClick={() => setRelPage(1)}
                      disabled={relPage === 1}
                    >
                      First
                    </button>
                    <button
                      className="btn btn-sm"
                      onClick={() => setRelPage((page) => Math.max(1, page - 1))}
                      disabled={relPage === 1}
                    >
                      Prev
                    </button>
                    <div style={{ alignSelf: 'center', fontSize: 12, color: '#52606d', padding: '0 6px' }}>
                      Page {relPage} of {totalRelationshipPages}
                    </div>
                    <button
                      className="btn btn-sm"
                      onClick={() => setRelPage((page) => Math.min(totalRelationshipPages, page + 1))}
                      disabled={relPage === totalRelationshipPages}
                    >
                      Next
                    </button>
                    <button
                      className="btn btn-sm"
                      onClick={() => setRelPage(totalRelationshipPages)}
                      disabled={relPage === totalRelationshipPages}
                    >
                      Last
                    </button>
                  </div>
                </div>
              )}
            </>
          ) : (
            <>
              <div
                style={{
                  display: 'grid',
                  gap: 12,
                  gridTemplateColumns: 'minmax(0, 1fr)',
                  marginBottom: 12,
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 10,
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                    <button
                      className="btn btn-sm dropdown-toggle"
                      type="button"
                      onClick={() => setShowColumnSelector((open) => !open)}
                      style={{
                        backgroundColor: '#0a8276',
                        color: '#fff',
                        fontWeight: 700,
                        border: '1px solid #0a8276',
                        padding: '6px 12px',
                        boxShadow: '0 2px 4px rgba(0,0,0,0.15)',
                      }}
                    >
                      View Columns ({visibleHeaders.length}/{nodeHeaders.length})
                    </button>
                  </div>

                  <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                    <label style={{ fontSize: 12, color: '#52606d', fontWeight: 700 }}>Rows per page</label>
                    <select
                      className="form-select form-select-sm"
                      style={{ width: 'auto' }}
                      value={itemsPerPage}
                      onChange={(event) => setItemsPerPage(parseInt(event.target.value, 10))}
                    >
                      {PAGE_SIZE_OPTIONS.map((size) => (
                        <option key={size} value={size}>
                          {size}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {showColumnSelector && (
                  <div
                    style={{
                      background: '#f8fafc',
                      border: '1px solid #d9e2ec',
                      borderRadius: 8,
                      padding: 12,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 10,
                        gap: 8,
                        flexWrap: 'wrap',
                      }}
                    >
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#243b53' }}>Visible Columns</div>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button className="btn btn-sm" onClick={() => setAllColumnsVisible(true)}>
                          Show All
                        </button>
                        <button className="btn btn-sm" onClick={() => setAllColumnsVisible(false)}>
                          Hide All
                        </button>
                      </div>
                    </div>
                    <div style={{ display: 'grid', gap: 8, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
                      {nodeHeaders.map((header) => (
                        <label
                          key={header}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            fontSize: 12,
                            color: '#243b53',
                          }}
                        >
                          <input
                            type="checkbox"
                            checked={visibleColumns[header] !== false}
                            onChange={() => toggleColumn(header)}
                          />
                          <span>{formatHeaderLabel(header)}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                )}

                {filterableHeaders.length > 0 && (
                  <div
                    style={{
                      background: '#f8fafc',
                      border: '1px solid #d9e2ec',
                      borderRadius: 8,
                      padding: 12,
                    }}
                  >
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#243b53', marginBottom: 10 }}>
                      Filters
                    </div>
                    <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
                      {filterableHeaders.map((header) => (
                        <select
                          key={header}
                          className="form-select form-select-sm"
                          value={filters[header] || ''}
                          onChange={(event) => handleFilterChange(header, event.target.value)}
                        >
                          <option value="">All {formatHeaderLabel(header)}</option>
                          {getDistinctValues(nodeRows, header).map((value) => (
                            <option key={value} value={value}>
                              {value.length > 42 ? `${value.slice(0, 42)}...` : value}
                            </option>
                          ))}
                        </select>
                      ))}
                    </div>
                    <div style={{ marginTop: 10 }}>
                      <button
                        className="btn btn-sm"
                        onClick={clearFilters}
                        disabled={Object.keys(filters).length === 0}
                      >
                        Clear Filters
                      </button>
                    </div>
                  </div>
                )}
              </div>

              <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, overflow: 'hidden' }}>
                {pagedNodeRows.length === 0 ? (
                  <div style={{ padding: 24, textAlign: 'center', color: '#7b8794' }}>
                    {activeReport === 'search'
                      ? Object.keys(filters).length > 0
                        ? 'No rows match the current filters.'
                        : graphLoading
                          ? 'Loading report rows...'
                          : graphError
                            ? 'Report rows could not be loaded from the current graph.'
                            : 'No report rows are available yet.'
                      : `No ${activeReport} rows are available.`}
                  </div>
                ) : (
                  <div style={{ overflowX: 'auto' }}>
                    <table className="table table-striped table-hover mb-0">
                      <thead className="sticky-top bg-light">
                        <tr>
                          {visibleHeaders.map((header) => (
                            <th
                              key={header}
                              onClick={() => handleSort(header)}
                              style={{
                                minWidth: 140,
                                borderBottom: '2px solid #0066B3',
                                cursor: activeReport === 'search' ? 'pointer' : 'default',
                                userSelect: 'none',
                              }}
                            >
                              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                                <span>{formatHeaderLabel(header)}</span>
                                {activeReport === 'search' && (
                                  <span style={{ fontSize: 12, opacity: 0.7 }}>
                                    {sortColumn === header ? (sortDirection === 'asc' ? '↑' : '↓') : '↕'}
                                  </span>
                                )}
                              </div>
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {pagedNodeRows.map((row, rowIndex) => (
                          <tr key={`${activeReport}-${rowIndex}`}>
                            {visibleHeaders.map((header) => (
                              <td key={header} style={{ maxWidth: 260 }}>
                                <div
                                  title={row[header] == null ? undefined : String(row[header])}
                                  style={{
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                  }}
                                >
                                  {formatCellValue(row[header])}
                                </div>
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {filteredNodeRows.length > 0 && (
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 12,
                    marginTop: 12,
                    flexWrap: 'wrap',
                  }}
                >
                  <div style={{ fontSize: 12, color: '#52606d' }}>
                    Showing {nodeStart} to {nodeEnd} of {filteredNodeRows.length}
                  </div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    <button
                      className="btn btn-sm"
                      onClick={() => setCurrentPage(1)}
                      disabled={currentPage === 1}
                    >
                      First
                    </button>
                    <button
                      className="btn btn-sm"
                      onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                      disabled={currentPage === 1}
                    >
                      Prev
                    </button>
                    <div style={{ fontSize: 12, color: '#52606d', padding: '0 6px' }}>
                      Page {currentPage} of {totalNodePages}
                    </div>
                    <button
                      className="btn btn-sm"
                      onClick={() => setCurrentPage((page) => Math.min(totalNodePages, page + 1))}
                      disabled={currentPage === totalNodePages}
                    >
                      Next
                    </button>
                    <button
                      className="btn btn-sm"
                      onClick={() => setCurrentPage(totalNodePages)}
                      disabled={currentPage === totalNodePages}
                    >
                      Last
                    </button>
                    <button
                      className="btn btn-sm"
                      onClick={() =>
                        downloadCsv(
                          `${activeReport}_page_${currentPage}_${new Date().toISOString().split('T')[0]}.csv`,
                          visibleHeaders,
                          pagedNodeRows
                        )
                      }
                      style={{
                        color: '#004B87',
                        background: '#e8f4fd',
                        border: '1px solid #004B87',
                        fontWeight: 700,
                        fontSize: 12,
                      }}
                    >
                      Export Page
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
};

export default ReportsTab;
