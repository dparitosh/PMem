import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Download, Network, Search } from 'lucide-react';
import { API_METHODS } from '../services/apiClient';
import { useOntologies } from '../contexts/OntologyContext';
import DataGridWidget from '../widgets/DataGridWidget';
import ErrorBoundary from './ErrorBoundary';

// ── Design tokens (corporate palette) ─────────────────────────────────────────
const C = {
  primary:      '#004B87',
  primaryDark:  '#003366',
  primaryLight: '#E8F1FC',
  green:        '#28A745',
  red:          '#D32F2F',
  textPrimary:  '#1A2B3C',
  textSec:      '#6C757D',
  textMuted:    '#ADB5BD',
  border:       '#E9ECEF',
  borderDark:   '#CED4DA',
  bg:           '#F8F9FA',
  surface:      '#FFFFFF',
};

// Relation type → badge color
const REL_COLORS = {
  equivalentClass: { bg: '#D4EDDA', text: '#155724', border: '#C3E6CB' },
  exactMatch:      { bg: '#D4EDDA', text: '#155724', border: '#C3E6CB' },
  closeMatch:      { bg: '#FFF3CD', text: '#856404', border: '#FFEEBA' },
  predicate:       { bg: '#D1ECF1', text: '#0C5460', border: '#BEE5EB' },
  label:           { bg: '#E2D9F3', text: '#4A1C7C', border: '#D1C4E9' },
  mapsTo:          { bg: '#CCE5FF', text: '#004085', border: '#B8DAFF' },
};

const SOURCE_FORMATS = [
  { id: 'plmxml', label: 'PLMXML' },
  { id: 'step', label: 'STEP' },
  { id: 'xmi', label: 'XMI' },
  { id: 'xml', label: 'XML' },
  { id: 'json', label: 'JSON' },
  { id: 'csv', label: 'CSV' },
  { id: 'excel', label: 'Excel' },
];

const TAXONOMY_HIERARCHY_TYPES = new Set(['subClassOf', 'broader', 'narrower', 'isA', 'parentOf', 'relatedTo', 'containedBy']);
const TAXONOMY_MAX_ROOTS = 18;
const TAXONOMY_MAX_CHILDREN = 12;
const TAXONOMY_MAX_DEPTH = 3;
const TAXONOMY_MAX_RENDERED_NODES = 220;

// ── CSV export ─────────────────────────────────────────────────────────────────
function exportCSV(rows, headers, filename) {
  const esc = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const lines = [headers.join(','), ...rows.map(r => headers.map(h => esc(r[h])).join(','))];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}

// ── Shared table style helpers ─────────────────────────────────────────────────
const TH = (extra = {}) => ({
  padding: '9px 14px',
  background: C.primary,
  color: '#fff',
  fontWeight: 700,
  fontSize: '11px',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  textAlign: 'left',
  whiteSpace: 'nowrap',
  borderRight: `1px solid ${C.primaryDark}`,
  position: 'sticky',
  top: 0,
  zIndex: 2,
  ...extra,
});
const TD = (extra = {}) => ({
  padding: '8px 14px',
  borderBottom: `1px solid ${C.border}`,
  fontSize: '13px',
  color: C.textPrimary,
  verticalAlign: 'middle',
  ...extra,
});

// ── RelBadge ───────────────────────────────────────────────────────────────────
function RelBadge({ type }) {
  const s = REL_COLORS[type] || { bg: C.bg, text: C.textSec, border: C.border };
  return (
    <span style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: '12px',
      background: s.bg, color: s.text, border: `1px solid ${s.border}`,
      fontWeight: 700, fontSize: '11px', whiteSpace: 'nowrap',
    }}>{type}</span>
  );
}

// ── Data Dictionary table ──────────────────────────────────────────────────────
function DataDictionaryTable({ nodes, filter, prefixFilter, onPrefixFilterChange }) {
  const [selectedRow, setSelectedRow] = useState(null);
  const lc = filter.toLowerCase();
  
  // Extract all unique prefixes
  const uniquePrefixes = useMemo(() => {
    const prefixes = new Set();
    nodes.forEach(n => {
      if (n.ontology_prefix) prefixes.add(n.ontology_prefix);
    });
    return Array.from(prefixes).sort();
  }, [nodes]);
  
  // Filter by both text search and prefix
  const visible = useMemo(() => {
    let filtered = nodes;
    
    // Apply text filter
    if (lc) {
      filtered = filtered.filter(n => 
        n.term_id.toLowerCase().includes(lc) || 
        (n.label || '').toLowerCase().includes(lc) || 
        (n.ontology_prefix || '').toLowerCase().includes(lc)
      );
    }
    
    // Apply prefix filter
    if (prefixFilter) {
      filtered = filtered.filter(n => n.ontology_prefix === prefixFilter);
    }
    
    return filtered;
  }, [nodes, lc, prefixFilter]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', color: C.textSec }}>{visible.length} of {nodes.length} terms</span>
          {uniquePrefixes.length > 0 && (
            <select
              value={prefixFilter || ''}
              onChange={e => onPrefixFilterChange(e.target.value || null)}
              style={{ padding: '5px 10px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', cursor: 'pointer', background: C.surface }}
            >
              <option key="all" value="">All Prefixes</option>
              {uniquePrefixes.map(prefix => (
                <option key={prefix} value={prefix}>{prefix}</option>
              ))}
            </select>
          )}
        </div>
        <button
          onClick={() => exportCSV(visible.map(n => ({ 'Term ID': n.term_id, 'Human-Readable Label': n.label || '', 'Ontology Prefix': n.ontology_prefix || '' })), ['Term ID', 'Human-Readable Label', 'Ontology Prefix'], 'data_dictionary.csv')}
          style={{ display: 'flex', alignItems: 'center', gap: '5px', padding: '6px 12px', background: C.primary, color: '#fff', border: 'none', borderRadius: '6px', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
        ><Download size={12} /> Export CSV</button>
      </div>
      <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'auto', maxHeight: '520px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '600px' }}>
          <thead>
            <tr>
              <th style={TH({ width: '40px', textAlign: 'center' })}>#</th>
              <th style={TH({ minWidth: '220px' })}>Term ID</th>
              <th style={TH({ minWidth: '200px' })}>Human-Readable Label</th>
              <th style={TH({ width: '130px' })}>Ontology Prefix</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr><td colSpan={4} style={{ ...TD(), textAlign: 'center', color: C.textMuted, padding: '32px' }}>No terms match the filter.</td></tr>
            )}
            {visible.map((n, i) => {
              const selected = selectedRow === n.term_id;
              return (
                <React.Fragment key={n.term_id}>
                  <tr
                    onClick={() => setSelectedRow(selected ? null : n.term_id)}
                    style={{ background: selected ? C.primaryLight : i % 2 === 0 ? C.surface : C.bg, cursor: 'pointer' }}
                    onMouseEnter={e => { if (!selected) e.currentTarget.style.background = C.primaryLight; }}
                    onMouseLeave={e => { if (!selected) e.currentTarget.style.background = i % 2 === 0 ? C.surface : C.bg; }}
                  >
                    <td style={TD({ textAlign: 'center', color: C.textMuted, fontSize: '11px' })}>{i + 1}</td>
                    <td style={TD({ fontFamily: 'monospace', fontSize: '12px', color: C.primary, fontWeight: 600 })}>{n.term_id}</td>
                    <td style={TD({ fontWeight: 500 })}>{n.label || <span style={{ color: C.textMuted }}>—</span>}</td>
                    <td style={TD()}>
                      {n.ontology_prefix
                        ? <span style={{ background: C.primaryLight, color: C.primary, padding: '2px 8px', borderRadius: '10px', fontWeight: 700, fontSize: '11px' }}>{n.ontology_prefix}</span>
                        : <span style={{ color: C.textMuted }}>—</span>}
                    </td>
                  </tr>
                  {selected && (
                    <tr style={{ background: '#EBF5FF' }}>
                      <td colSpan={4} style={{ padding: '12px 20px', borderBottom: `1px solid ${C.border}` }}>
                        <div style={{ fontWeight: 700, fontSize: '12px', color: C.primary, marginBottom: '8px' }}>Full Term URI</div>
                        <code style={{ fontSize: '12px', color: C.textPrimary, wordBreak: 'break-all' }}>{n.term_id}</code>
                        {n.definition && (
                          <>
                            <div style={{ fontWeight: 700, fontSize: '12px', color: C.primary, marginTop: '10px', marginBottom: '4px' }}>Definition</div>
                            <span style={{ fontSize: '13px' }}>{n.definition}</span>
                          </>
                        )}
                        {n.synonyms && n.synonyms.length > 0 && (
                          <>
                            <div style={{ fontWeight: 700, fontSize: '12px', color: C.primary, marginTop: '10px', marginBottom: '4px' }}>Synonyms</div>
                            <span style={{ fontSize: '13px' }}>{n.synonyms.join(', ')}</span>
                          </>
                        )}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Vocabulary / Mappings table ────────────────────────────────────────────────
function VocabularyTable({ edges, filter }) {
  const [selectedRow, setSelectedRow] = useState(null);
  const lc = filter.toLowerCase();
  const visible = useMemo(() => {
    if (!lc) return edges;
    return edges.filter(e => {
      return (
        e.source_term.toLowerCase().includes(lc) ||
        e.target_term.toLowerCase().includes(lc) ||
        e.mapping_type.toLowerCase().includes(lc) ||
        (e.source_label || '').toLowerCase().includes(lc) ||
        (e.target_label || '').toLowerCase().includes(lc)
      );
    });
  }, [edges, lc]);

  const typeGroups = useMemo(() => {
    const m = {};
    edges.forEach(e => { m[e.mapping_type] = (m[e.mapping_type] || 0) + 1; });
    return m;
  }, [edges]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', color: C.textSec, marginRight: '4px' }}>Relation types:</span>
          {Object.entries(typeGroups).map(([type, count]) => (
            <span key={type} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <RelBadge type={type} />
              <span style={{ fontSize: '11px', color: C.textMuted }}>({count})</span>
            </span>
          ))}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '12px', color: C.textSec }}>{visible.length} of {edges.length} mappings</span>
          <button
            onClick={() => exportCSV(
              visible.map(e => ({
                'Source Term':  e.source_term,
                'Source Label': e.source_label || '',
                'Mapping Type': e.mapping_type,
                'Target Term':  e.target_term,
                'Target Label': e.target_label || '',
              })),
              ['Source Term', 'Source Label', 'Mapping Type', 'Target Term', 'Target Label'],
              'vocabulary_mappings.csv'
            )}
            style={{ display: 'flex', alignItems: 'center', gap: '5px', padding: '6px 12px', background: C.primary, color: '#fff', border: 'none', borderRadius: '6px', fontSize: '12px', fontWeight: 600, cursor: 'pointer' }}
          ><Download size={12} /> Export CSV</button>
        </div>
      </div>
      <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'auto', maxHeight: '520px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '700px' }}>
          <thead>
            <tr>
              <th style={TH({ width: '40px', textAlign: 'center' })}>#</th>
              <th style={TH({ minWidth: '200px' })}>Source Concept</th>
              <th style={TH({ width: '150px', textAlign: 'center' })}>Mapping Type</th>
              <th style={TH({ minWidth: '200px' })}>Target Concept</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr><td colSpan={4} style={{ ...TD(), textAlign: 'center', color: C.textMuted, padding: '32px' }}>No mappings match the filter.</td></tr>
            )}
            {visible.map((e, i) => {
              const rowId = `${e.source_term}__${e.mapping_type}__${e.target_term}`;
              const selected = selectedRow === rowId;
              return (
                <React.Fragment key={e.source_term + '-' + e.mapping_type + '-' + e.target_term}>
                  <tr
                    onClick={() => setSelectedRow(selected ? null : rowId)}
                    style={{ background: selected ? C.primaryLight : i % 2 === 0 ? C.surface : C.bg, cursor: 'pointer' }}
                    onMouseEnter={ev => { if (!selected) ev.currentTarget.style.background = C.primaryLight; }}
                    onMouseLeave={ev => { if (!selected) ev.currentTarget.style.background = i % 2 === 0 ? C.surface : C.bg; }}
                  >
                    <td style={TD({ textAlign: 'center', color: C.textMuted, fontSize: '11px' })}>{i + 1}</td>
                    <td style={TD()}>
                      <div style={{ fontWeight: 600, fontSize: '13px' }}>{e.source_label || e.source_term.split(':').pop()}</div>
                      <div style={{ fontFamily: 'monospace', fontSize: '10px', color: C.textSec, marginTop: '2px' }}>{e.source_term}</div>
                    </td>
                    <td style={TD({ textAlign: 'center' })}><RelBadge type={e.mapping_type} /></td>
                    <td style={TD()}>
                      <div style={{ fontWeight: 600, fontSize: '13px' }}>{e.target_label || e.target_term.split(':').pop()}</div>
                      <div style={{ fontFamily: 'monospace', fontSize: '10px', color: C.textSec, marginTop: '2px' }}>{e.target_term}</div>
                    </td>
                  </tr>
                  {selected && (
                    <tr style={{ background: '#EBF5FF' }}>
                      <td colSpan={4} style={{ padding: '12px 20px', borderBottom: `1px solid ${C.border}` }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: '16px', alignItems: 'start' }}>
                          <div>
                            <div style={{ fontSize: '11px', fontWeight: 700, color: C.textSec, textTransform: 'uppercase', marginBottom: '4px' }}>Source</div>
                            <div style={{ fontWeight: 700, color: C.primary }}>{e.source_label || e.source_term.split(':').pop()}</div>
                            <code style={{ fontSize: '11px', color: C.textSec, wordBreak: 'break-all' }}>{e.source_term}</code>
                          </div>
                          <div style={{ textAlign: 'center', paddingTop: '10px' }}>
                            <RelBadge type={e.mapping_type} />
                            <div style={{ fontSize: '18px', color: C.textMuted, marginTop: '4px' }}>→</div>
                          </div>
                          <div>
                            <div style={{ fontSize: '11px', fontWeight: 700, color: C.textSec, textTransform: 'uppercase', marginBottom: '4px' }}>Target</div>
                            <div style={{ fontWeight: 700, color: C.primary }}>{e.target_label || e.target_term.split(':').pop()}</div>
                            <code style={{ fontSize: '11px', color: C.textSec, wordBreak: 'break-all' }}>{e.target_term}</code>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function TaxonomyView({ nodes, edges, filter, taxonomy, reasoning }) {
  const lc = filter.toLowerCase();
  const termIdFromRef = useCallback((ref) => {
    const iri = String(ref?.iri || ref?.uri || ref?.term_id || ref?.id || '').trim();
    if (!iri) return '';
    const prefix = String(ref?.ontology_prefix || taxonomy?.ontology_prefix || '').trim();
    const local = String(ref?.label || iri.split(/[/#]/).pop() || iri).trim();
    if (!ref?.term_id && /^tmp[a-z0-9_]{6,}$/i.test(local)) return '';
    return ref?.term_id || (prefix ? `${prefix}:${local}` : iri);
  }, [taxonomy]);
  const refLabel = useCallback((ref) => {
    const raw = String(ref?.label || ref?.name || ref?.term_id || ref?.iri || ref?.uri || '').split(/[/#]/).pop();
    return /^tmp[a-z0-9_]{6,}$/i.test(raw) ? '' : raw;
  }, []);

  const reasoningClassNodes = useMemo(() => (reasoning?.classes || []).map((cls) => ({
    term_id: termIdFromRef(cls),
    uri: cls.iri || cls.uri || '',
    label: refLabel(cls),
    definition: cls.definition || cls.comment || '',
    ontology_prefix: cls.ontology_prefix || taxonomy?.ontology_prefix || '',
    source: 'owlready2-class',
  })).filter((node) => node.term_id), [reasoning, refLabel, taxonomy, termIdFromRef]);

  const reasoningPropertyNodes = useMemo(() => [
    ...(reasoning?.object_properties || []).map((prop) => ({ ...prop, property_kind: 'ObjectProperty' })),
    ...(reasoning?.datatype_properties || []).map((prop) => ({ ...prop, property_kind: 'DatatypeProperty' })),
    ...(reasoning?.annotation_properties || []).map((prop) => ({ ...prop, property_kind: 'AnnotationProperty' })),
  ].map((prop) => ({
    term_id: termIdFromRef(prop),
    uri: prop.iri || prop.uri || '',
    label: refLabel(prop),
    definition: prop.definition || prop.comment || '',
    ontology_prefix: prop.ontology_prefix || taxonomy?.ontology_prefix || '',
    source: String(prop.property_kind || 'Property').toLowerCase(),
  })).filter((node) => node.term_id), [reasoning, refLabel, taxonomy, termIdFromRef]);

  const taxonomyNodes = useMemo(() => {
    const rawNodes = taxonomy?.nodes?.length ? taxonomy.nodes : nodes;
    const merged = new Map();
    [...(rawNodes || []), ...reasoningClassNodes, ...reasoningPropertyNodes].forEach((node) => {
      if (node?.term_id && !merged.has(node.term_id)) merged.set(node.term_id, node);
    });
    return Array.from(merged.values());
  }, [nodes, reasoningClassNodes, reasoningPropertyNodes, taxonomy]);

  const taxonomyEdges = useMemo(() => {
    const rawEdges = taxonomy?.edges?.length ? taxonomy.edges : edges;
    const normalized = Array.isArray(rawEdges) ? [...rawEdges] : [];

    (reasoning?.subclass_edges || []).forEach((edge) => {
      normalized.push({
        source_term: termIdFromRef({ iri: edge.source, label: edge.source_label, ontology_prefix: taxonomy?.ontology_prefix }),
        source_label: edge.source_label || refLabel({ iri: edge.source }),
        target_term: termIdFromRef({ iri: edge.target, label: edge.target_label, ontology_prefix: taxonomy?.ontology_prefix }),
        target_label: edge.target_label || refLabel({ iri: edge.target }),
        mapping_type: edge.type || 'subClassOf',
      });
    });

    [...(reasoning?.object_properties || []), ...(reasoning?.datatype_properties || []), ...(reasoning?.annotation_properties || [])].forEach((prop) => {
      const propTerm = termIdFromRef(prop);
      (prop.domain || []).forEach((domain) => {
        normalized.push({
          source_term: propTerm,
          source_label: refLabel(prop),
          target_term: termIdFromRef(domain),
          target_label: refLabel(domain),
          mapping_type: 'DOMAIN',
        });
      });
      (prop.range || []).forEach((range) => {
        normalized.push({
          source_term: propTerm,
          source_label: refLabel(prop),
          target_term: termIdFromRef(range),
          target_label: refLabel(range),
          mapping_type: 'RANGE',
        });
      });
    });

    return normalized.filter((edge, index, list) => {
      const key = `${edge.source_term}|${edge.mapping_type}|${edge.target_term}`;
      return edge.source_term && edge.target_term && list.findIndex((item) => `${item.source_term}|${item.mapping_type}|${item.target_term}` === key) === index;
    });
  }, [edges, reasoning, refLabel, taxonomy, termIdFromRef]);

  const taxonomySummary = taxonomy?.summary || null;
  const visibleNodes = useMemo(() => {
    if (!lc) return taxonomyNodes;
    return taxonomyNodes.filter((node) =>
      String(node.term_id || '').toLowerCase().includes(lc) ||
      String(node.label || '').toLowerCase().includes(lc) ||
      String(node.ontology_prefix || '').toLowerCase().includes(lc)
    );
  }, [taxonomyNodes, lc]);

  const prefixGroups = useMemo(() => {
    const groups = new Map();
    visibleNodes.forEach((node) => {
      const prefix = node.ontology_prefix || 'unassigned';
      if (!groups.has(prefix)) groups.set(prefix, []);
      groups.get(prefix).push(node);
    });
    return Array.from(groups.entries()).map(([prefix, terms]) => ({
      prefix,
      terms: terms.sort((a, b) => (a.label || a.term_id).localeCompare(b.label || b.term_id)),
    }));
  }, [visibleNodes]);

  const hierarchyModel = useMemo(() => {
    const visibleIds = new Set(visibleNodes.map((node) => node.term_id));
    const childrenByParent = new Map();
    const parentIds = new Set();
    const labelsById = new Map(
      visibleNodes.map((node) => [node.term_id, node.label || node.term_id])
    );

    taxonomyEdges.forEach((edge) => {
      if (!TAXONOMY_HIERARCHY_TYPES.has(edge.mapping_type)) return;
      if (!visibleIds.has(edge.source_term) || !visibleIds.has(edge.target_term)) return;
      if (!childrenByParent.has(edge.target_term)) childrenByParent.set(edge.target_term, []);
      childrenByParent.get(edge.target_term).push(edge.source_term);
      parentIds.add(edge.source_term);
    });

    const roots = visibleNodes
      .filter((node) => !parentIds.has(node.term_id))
      .map((node) => node.term_id)
      .sort((left, right) => {
        return (labelsById.get(left) || left).localeCompare(labelsById.get(right) || right);
      });

    childrenByParent.forEach((children, key) => {
      children.sort((left, right) => {
        return (labelsById.get(left) || left).localeCompare(labelsById.get(right) || right);
      });
      childrenByParent.set(key, children);
    });

    return { childrenByParent, roots };
  }, [visibleNodes, taxonomyEdges]);

  const relationCount = taxonomySummary?.taxonomy_links ?? taxonomyEdges.filter((edge) =>
    TAXONOMY_HIERARCHY_TYPES.has(edge.mapping_type)
  ).length;

  const nodeById = useMemo(
    () => new Map(visibleNodes.map((node) => [node.term_id, node])),
    [visibleNodes]
  );

  let renderedNodeCount = 0;
  const renderTree = (termId, depth = 0, seen = new Set()) => {
    if (renderedNodeCount >= TAXONOMY_MAX_RENDERED_NODES || depth > TAXONOMY_MAX_DEPTH) return null;
    if (seen.has(termId)) return null;
    const term = nodeById.get(termId);
    if (!term) return null;

    renderedNodeCount += 1;
    const nextSeen = new Set(seen);
    nextSeen.add(termId);
    const children = hierarchyModel.childrenByParent.get(termId) || [];
    const childrenToRender = depth >= TAXONOMY_MAX_DEPTH
      ? []
      : children.slice(0, TAXONOMY_MAX_CHILDREN);
    const hiddenChildrenCount = Math.max(children.length - childrenToRender.length, 0);

    return (
      <div key={`${termId}-${depth}`} style={{ display: 'grid', gap: '6px' }}>
        <div
          title={term.term_id}
          style={{
            display: 'grid',
            gridTemplateColumns: `${16 + (depth * 18)}px minmax(0, 1fr)`,
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'center' }}>
            <span style={{
              width: depth === 0 ? 8 : 10,
              height: depth === 0 ? 8 : 2,
              borderRadius: depth === 0 ? '999px' : '999px',
              background: depth === 0 ? C.primary : C.borderDark,
              display: 'inline-block',
            }} />
          </div>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            minWidth: 0,
            flexWrap: 'wrap',
          }}>
            <span style={{
              fontSize: '12px',
              fontWeight: depth < 2 ? 700 : 600,
              color: C.textPrimary,
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              {term.label || term.term_id.split(':').pop()}
            </span>
            <span style={{
              fontSize: '10px',
              color: C.textSec,
              background: C.bg,
              border: `1px solid ${C.border}`,
              borderRadius: '999px',
              padding: '2px 6px',
              whiteSpace: 'nowrap',
            }}>
              {children.length} child{children.length === 1 ? '' : 'ren'}
            </span>
          </div>
        </div>
        {childrenToRender.length > 0 && (
          <div style={{ display: 'grid', gap: '6px' }}>
            {childrenToRender.map((childId) => renderTree(childId, depth + 1, nextSeen))}
          </div>
        )}
        {(hiddenChildrenCount > 0 || depth === TAXONOMY_MAX_DEPTH) && (
          <div style={{ paddingLeft: `${24 + (depth * 18)}px`, fontSize: '11px', color: C.textMuted }}>
            {depth === TAXONOMY_MAX_DEPTH
              ? 'Refine the filter to inspect deeper taxonomy branches.'
              : `${hiddenChildrenCount} additional child nodes hidden until you narrow the filter.`}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ display: 'grid', gap: '10px' }}>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
        gap: '1px',
        border: `1px solid ${C.border}`,
        borderRadius: '8px',
        overflow: 'hidden',
        background: C.border,
      }}>
        {[
          { label: 'Terms', value: visibleNodes.length },
          { label: 'Namespaces', value: prefixGroups.length },
          { label: 'Taxonomy Links', value: relationCount },
          { label: 'OWL Classes', value: reasoning?.summary?.classes ?? taxonomy?.reasoning_summary?.classes ?? 0 },
          { label: 'OWL Properties', value: (reasoning?.summary?.object_properties ?? taxonomy?.reasoning_summary?.object_properties ?? 0) + (reasoning?.summary?.datatype_properties ?? taxonomy?.reasoning_summary?.datatype_properties ?? 0) },
          { label: 'Individuals', value: reasoning?.summary?.individuals ?? taxonomy?.reasoning_summary?.individuals ?? 0 },
        ].map((item) => (
          <div key={item.label} style={{ background: C.surface, padding: '10px 12px' }}>
            <div style={{ fontSize: '10px', fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>{item.label}</div>
            <div style={{ fontSize: '22px', fontWeight: 800, color: C.textPrimary, marginTop: '4px' }}>{item.value}</div>
          </div>
        ))}
      </div>

      {reasoning?.status === 'success' && (
        <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', background: C.surface, overflow: 'hidden' }}>
          <div style={{ padding: '9px 12px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
            <span style={{ fontSize: '12px', fontWeight: 700, color: C.textPrimary }}>Owlready2 Semantics</span>
            <span style={{ fontSize: '10px', fontWeight: 700, color: C.textSec, background: C.bg, border: `1px solid ${C.border}`, borderRadius: '999px', padding: '2px 7px' }}>
              {reasoning.summary?.classes || 0} classes · {reasoning.summary?.subclass_edges || 0} subclass links
            </span>
          </div>
          <div style={{ padding: '10px 12px', display: 'grid', gap: '10px' }}>
            <div style={{ display: 'grid', gap: '6px' }}>
              <div style={{ fontSize: '11px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Classes</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {(reasoning.classes || []).slice(0, 10).map((cls) => (
                  <span key={cls.iri} title={cls.iri} style={{ fontSize: '11px', color: C.textPrimary, background: C.primaryLight, border: `1px solid ${C.border}`, borderRadius: '999px', padding: '3px 7px' }}>
                    {cls.label}
                  </span>
                ))}
              </div>
            </div>
            <div style={{ display: 'grid', gap: '6px' }}>
              <div style={{ fontSize: '11px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Object Properties</div>
              <div style={{ display: 'grid', gap: '6px' }}>
                {(reasoning.object_properties || []).slice(0, 6).map((prop) => (
                  <div key={prop.iri} style={{ fontSize: '12px', color: C.textPrimary, background: C.bg, border: `1px solid ${C.border}`, borderRadius: '6px', padding: '6px 8px' }}>
                    <strong>{prop.label}</strong>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      Domain: {(prop.domain || []).map((d) => d.label).join(', ') || 'None'} · Range: {(prop.range || []).map((r) => r.label).join(', ') || 'None'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div style={{ display: 'grid', gap: '6px' }}>
              <div style={{ fontSize: '11px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Individuals</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {(reasoning.individuals || []).slice(0, 10).map((individual) => (
                  <span key={individual.iri} title={individual.iri} style={{ fontSize: '11px', color: C.textPrimary, background: C.surface, border: `1px solid ${C.border}`, borderRadius: '999px', padding: '3px 7px' }}>
                    {individual.label}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', background: C.surface, overflow: 'hidden' }}>
        <div style={{ padding: '9px 12px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', gap: '8px', alignItems: 'center' }}>
          <span style={{ fontSize: '12px', fontWeight: 700, color: C.textPrimary }}>Taxonomy Browser</span>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'flex-end' }}>
            {taxonomy?.extraction_source && (
              <span style={{ fontSize: '10px', fontWeight: 700, color: C.textSec, background: C.bg, border: `1px solid ${C.border}`, borderRadius: '999px', padding: '2px 7px' }}>
                Taxonomy: {taxonomy.extraction_source}
              </span>
            )}
            {reasoning?.engine === 'owlready2' && (
              <span style={{ fontSize: '10px', fontWeight: 700, color: C.primary, background: C.primaryLight, border: `1px solid ${C.border}`, borderRadius: '999px', padding: '2px 7px' }}>
                Owlready2 semantics
              </span>
            )}
          </div>
        </div>
        {Array.isArray(reasoning?.diagnostics) && reasoning.diagnostics.length > 0 && (
          <div style={{ padding: '10px 12px', borderBottom: `1px solid ${C.border}`, background: C.bg, display: 'grid', gap: '6px' }}>
            <div style={{ fontSize: '11px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Reasoning diagnostics</div>
            {reasoning.diagnostics.slice(0, 3).map((item, idx) => (
              <div key={`${item.category || 'diag'}-${idx}`} style={{ fontSize: '12px', color: C.textPrimary, lineHeight: 1.45 }}>
                <strong style={{ color: item.severity === 'warning' ? C.red : C.primary }}>{item.category || item.severity}</strong>: {item.message}
              </div>
            ))}
          </div>
        )}
        <div style={{ maxHeight: '520px', overflow: 'auto', padding: '10px 12px', display: 'grid', gap: '10px' }}>
          {relationCount > 0 && visibleNodes.length > TAXONOMY_MAX_RENDERED_NODES && (
            <div style={{
              padding: '10px 12px',
              borderRadius: '8px',
              border: `1px solid ${C.border}`,
              background: C.bg,
              color: C.textSec,
              fontSize: '12px',
            }}>
              Showing a compact taxonomy outline for this ontology. Use the filter to inspect a narrower branch.
            </div>
          )}
          {prefixGroups.length === 0 && (
            <div style={{ color: C.textMuted, fontSize: '13px', padding: '24px', textAlign: 'center' }}>
              No taxonomy terms match the current filter.
            </div>
          )}
          {prefixGroups.map(({ prefix, terms }) => {
            const prefixTermIds = new Set(terms.map((term) => term.term_id));
            const prefixRoots = hierarchyModel.roots.filter((termId) => prefixTermIds.has(termId));
            const hasHierarchy = relationCount > 0 && prefixRoots.length > 0;
            return (
              <section key={prefix} style={{ border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'hidden' }}>
                <div style={{ background: C.bg, padding: '8px 10px', display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                  <span style={{ fontSize: '12px', fontWeight: 800, color: C.primary }}>{prefix}</span>
                  <span style={{ fontSize: '11px', color: C.textSec }}>{terms.length} terms</span>
                </div>
                <div style={{ padding: '8px 10px', display: 'grid', gap: '8px' }}>
                  {hasHierarchy ? prefixRoots.slice(0, TAXONOMY_MAX_ROOTS).map((termId) => (
                    <div key={`${prefix}-${termId}`} style={{ padding: '4px 0' }}>
                      {renderTree(termId)}
                    </div>
                  )) : (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                      {terms.slice(0, 80).map((term) => (
                        <span
                          key={term.term_id}
                          title={term.term_id}
                          style={{
                            fontSize: '11px',
                            color: C.textPrimary,
                            background: C.bg,
                            border: `1px solid ${C.border}`,
                            borderRadius: '999px',
                            padding: '3px 7px',
                            maxWidth: '220px',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }}
                        >
                          {term.label || term.term_id.split(':').pop()}
                        </span>
                      ))}
                    </div>
                  )}
                  {hasHierarchy && prefixRoots.length > TAXONOMY_MAX_ROOTS && (
                    <div style={{ fontSize: '11px', color: C.textMuted }}>
                      {prefixRoots.length - TAXONOMY_MAX_ROOTS} additional root branches hidden until you narrow the filter.
                    </div>
                  )}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function ProtegeOntologyBrowser({ nodes, edges, filter, taxonomy, reasoning }) {
  const [selectedTermId, setSelectedTermId] = useState('');
  const [tableMode, setTableMode] = useState('classes');
  const lc = filter.trim().toLowerCase();
  const gridTextCell = useMemo(() => ({
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    lineHeight: '32px',
  }), []);
  const termIdFromRef = useCallback((ref) => {
    const iri = String(ref?.iri || ref?.uri || ref?.term_id || ref?.id || '').trim();
    if (!iri) return '';
    const prefix = String(ref?.ontology_prefix || taxonomy?.ontology_prefix || '').trim();
    const local = String(ref?.label || iri.split(/[/#]/).pop() || iri).trim();
    if (!ref?.term_id && /^tmp[a-z0-9_]{6,}$/i.test(local)) return '';
    return ref?.term_id || (prefix ? `${prefix}:${local}` : iri);
  }, [taxonomy]);

  const refLabel = useCallback((ref) => {
    const raw = String(ref?.label || ref?.name || ref?.term_id || ref?.iri || ref?.uri || '').split(/[/#]/).pop();
    return /^tmp[a-z0-9_]{6,}$/i.test(raw) ? '' : raw;
  }, []);

  const reasoningClassNodes = useMemo(() => (reasoning?.classes || []).map((cls) => ({
    term_id: termIdFromRef(cls),
    uri: cls.iri || cls.uri || '',
    label: refLabel(cls),
    definition: cls.definition || '',
    ontology_prefix: cls.ontology_prefix || taxonomy?.ontology_prefix || '',
    source: 'owlready2-class',
  })).filter((node) => node.term_id), [reasoning, refLabel, taxonomy, termIdFromRef]);

  const reasoningPropertyNodes = useMemo(() => [
    ...(reasoning?.object_properties || []).map((prop) => ({ ...prop, property_kind: 'ObjectProperty' })),
    ...(reasoning?.datatype_properties || []).map((prop) => ({ ...prop, property_kind: 'DatatypeProperty' })),
    ...(reasoning?.annotation_properties || []).map((prop) => ({ ...prop, property_kind: 'AnnotationProperty' })),
  ].map((prop) => ({
    term_id: termIdFromRef(prop),
    uri: prop.iri || prop.uri || '',
    label: refLabel(prop),
    definition: prop.definition || '',
    ontology_prefix: prop.ontology_prefix || taxonomy?.ontology_prefix || '',
    source: prop.property_kind === 'DatatypeProperty' ? 'owlready2-datatype-property' : 'owlready2-object-property',
  })).filter((node) => node.term_id), [reasoning, refLabel, taxonomy, termIdFromRef]);

  const taxonomyNodes = useMemo(() => {
    const rawNodes = taxonomy?.nodes?.length ? taxonomy.nodes : nodes;
    const merged = new Map();
    [...(rawNodes || []), ...reasoningClassNodes, ...reasoningPropertyNodes].forEach((node) => {
      if (node?.term_id && !merged.has(node.term_id)) merged.set(node.term_id, node);
    });
    return Array.from(merged.values());
  }, [nodes, reasoningClassNodes, reasoningPropertyNodes, taxonomy]);

  const taxonomyEdges = useMemo(() => {
    const rawEdges = taxonomy?.edges?.length ? taxonomy.edges : edges;
    const normalized = Array.isArray(rawEdges) ? [...rawEdges] : [];

    (reasoning?.subclass_edges || []).forEach((edge) => {
      normalized.push({
        source_term: termIdFromRef({ iri: edge.source, label: edge.source_label, ontology_prefix: taxonomy?.ontology_prefix }),
        source_label: edge.source_label || refLabel({ iri: edge.source }),
        target_term: termIdFromRef({ iri: edge.target, label: edge.target_label, ontology_prefix: taxonomy?.ontology_prefix }),
        target_label: edge.target_label || refLabel({ iri: edge.target }),
        mapping_type: edge.type || 'subClassOf',
      });
    });

    [...(reasoning?.object_properties || []), ...(reasoning?.datatype_properties || [])].forEach((prop) => {
      const propTerm = termIdFromRef(prop);
      (prop.domain || []).forEach((domain) => {
        normalized.push({
          source_term: propTerm,
          source_label: refLabel(prop),
          target_term: termIdFromRef(domain),
          target_label: refLabel(domain),
          mapping_type: 'DOMAIN',
        });
      });
      (prop.range || []).forEach((range) => {
        normalized.push({
          source_term: propTerm,
          source_label: refLabel(prop),
          target_term: termIdFromRef(range),
          target_label: refLabel(range),
          mapping_type: 'RANGE',
        });
      });
    });

    return normalized.filter((edge, index, list) => {
      const key = `${edge.source_term}|${edge.mapping_type}|${edge.target_term}`;
      return edge.source_term && edge.target_term && list.findIndex((item) => `${item.source_term}|${item.mapping_type}|${item.target_term}` === key) === index;
    });
  }, [edges, reasoning, refLabel, taxonomy, termIdFromRef]);

  const visibleNodes = useMemo(() => {
    if (!lc) return taxonomyNodes;
    return taxonomyNodes.filter((node) =>
      String(node.term_id || '').toLowerCase().includes(lc) ||
      String(node.label || '').toLowerCase().includes(lc) ||
      String(node.ontology_prefix || '').toLowerCase().includes(lc)
    );
  }, [taxonomyNodes, lc]);

  const nodeById = useMemo(() => new Map(taxonomyNodes.map((node) => [node.term_id, node])), [taxonomyNodes]);

  const hierarchy = useMemo(() => {
    const visibleIds = new Set(visibleNodes.map((node) => node.term_id));
    const childrenByParent = new Map();
    const parentByChild = new Map();

    taxonomyEdges.forEach((edge) => {
      if (!TAXONOMY_HIERARCHY_TYPES.has(edge.mapping_type)) return;
      if (!visibleIds.has(edge.source_term) || !visibleIds.has(edge.target_term)) return;
      if (!childrenByParent.has(edge.target_term)) childrenByParent.set(edge.target_term, []);
      childrenByParent.get(edge.target_term).push(edge.source_term);
      if (!parentByChild.has(edge.source_term)) parentByChild.set(edge.source_term, []);
      parentByChild.get(edge.source_term).push(edge.target_term);
    });

    const labelOf = (termId) => nodeById.get(termId)?.label || String(termId || '').split(':').pop() || termId;
    childrenByParent.forEach((children, parentId) => {
      children.sort((left, right) => labelOf(left).localeCompare(labelOf(right)));
      childrenByParent.set(parentId, children);
    });

    const roots = visibleNodes
      .filter((node) => !parentByChild.has(node.term_id))
      .map((node) => node.term_id)
      .sort((left, right) => labelOf(left).localeCompare(labelOf(right)));

    const rows = [];
    const seen = new Set();
    const pushBranch = (termId, depth = 0, path = []) => {
      if (seen.has(termId) || rows.length >= 800) return;
      seen.add(termId);
      const node = nodeById.get(termId);
      if (!node) return;
      const children = childrenByParent.get(termId) || [];
      rows.push({
        id: termId,
        termId,
        label: node.label || String(termId).split(':').pop(),
        prefix: node.ontology_prefix || '',
        depth,
        indent: `${'  '.repeat(Math.min(depth, 8))}${depth > 0 ? '|- ' : ''}`,
        children: children.length,
        path: [...path, node.label || termId].join(' / '),
      });
      children.forEach((childId) => pushBranch(childId, depth + 1, [...path, node.label || termId]));
    };

    roots.slice(0, 120).forEach((rootId) => pushBranch(rootId));
    visibleNodes.forEach((node) => {
      if (!seen.has(node.term_id) && rows.length < 800) pushBranch(node.term_id);
    });

    return { childrenByParent, parentByChild, roots, rows };
  }, [taxonomyEdges, visibleNodes, nodeById]);

  const selectedTerm = useMemo(() => {
    if (selectedTermId && nodeById.has(selectedTermId)) return nodeById.get(selectedTermId);
    const connectedIds = new Set();
    taxonomyEdges.forEach((edge) => {
      if (edge?.source_term) connectedIds.add(edge.source_term);
      if (edge?.target_term) connectedIds.add(edge.target_term);
    });
    const connectedVisible = visibleNodes.find((node) => connectedIds.has(node.term_id));
    return connectedVisible || visibleNodes[0] || null;
  }, [nodeById, selectedTermId, taxonomyEdges, visibleNodes]);

  const edgeRows = useMemo(() => taxonomyEdges.map((edge, index) => {
    const source = nodeById.get(edge.source_term);
    const target = nodeById.get(edge.target_term);
    return {
      id: `${edge.source_term}-${edge.mapping_type}-${edge.target_term}-${index}`,
      sourceId: edge.source_term,
      source: source?.label || String(edge.source_term || '').split(':').pop(),
      axiom: edge.mapping_type || 'relatedTo',
      targetId: edge.target_term,
      target: target?.label || String(edge.target_term || '').split(':').pop(),
      prefix: source?.ontology_prefix || target?.ontology_prefix || '',
    };
  }), [taxonomyEdges, nodeById]);

  const classRows = useMemo(() => visibleNodes.filter((node) => !String(node.source || '').includes('property')).map((node) => {
    const parents = hierarchy.parentByChild.get(node.term_id) || [];
    const children = hierarchy.childrenByParent.get(node.term_id) || [];
    return {
      id: node.term_id,
      termId: node.term_id,
      label: node.label || String(node.term_id || '').split(':').pop(),
      prefix: node.ontology_prefix || '',
      parents: parents.map((id) => nodeById.get(id)?.label || id).join(', ') || 'Thing',
      children: children.length,
      definition: node.definition || node.comment || '',
      type: 'Class',
      node,
    };
  }), [visibleNodes, hierarchy, nodeById]);

  const reasoningPropertyRows = useMemo(() => [
    ...(reasoning?.object_properties || []).map((prop) => ({ ...prop, property_kind: 'ObjectProperty' })),
    ...(reasoning?.datatype_properties || []).map((prop) => ({ ...prop, property_kind: 'DatatypeProperty' })),
    ...(reasoning?.annotation_properties || []).map((prop) => ({ ...prop, property_kind: 'AnnotationProperty' })),
  ].map((prop) => ({
    id: termIdFromRef(prop),
    property: refLabel(prop),
    prefix: prop.ontology_prefix || taxonomy?.ontology_prefix || '',
    kind: prop.property_kind,
    domain: (prop.domain || []).map(refLabel).filter(Boolean).join(', ') || 'Not declared',
    range: (prop.range || []).map(refLabel).filter(Boolean).join(', ') || 'Not declared',
    axiomCount: (prop.domain || []).length + (prop.range || []).length,
  })).filter((row) => row.id), [reasoning, refLabel, taxonomy, termIdFromRef]);

  const objectPropertyRows = useMemo(() => {
    const byProperty = new Map();
    edgeRows.forEach((edge) => {
      if (!['DOMAIN', 'RANGE', 'domain', 'range', 'predicate', 'property_of'].includes(edge.axiom)) return;
      if (!byProperty.has(edge.sourceId)) {
        byProperty.set(edge.sourceId, {
          id: edge.sourceId,
          property: edge.source,
          prefix: edge.prefix,
          domain: [],
          range: [],
          axiomCount: 0,
        });
      }
      const row = byProperty.get(edge.sourceId);
      row.axiomCount += 1;
      if (String(edge.axiom).toUpperCase() === 'DOMAIN') row.domain.push(edge.target);
      if (String(edge.axiom).toUpperCase() === 'RANGE') row.range.push(edge.target);
    });
    const rowsFromEdges = Array.from(byProperty.values()).map((row) => ({
      ...row,
      domain: row.domain.join(', ') || 'Not declared',
      range: row.range.join(', ') || 'Not declared',
      kind: 'Property',
    }));
    if (reasoningPropertyRows.length) return reasoningPropertyRows;
    if (rowsFromEdges.length) return rowsFromEdges;
    return visibleNodes
      .filter((node) => String(node.source || '').includes('property'))
      .map((node) => ({
        id: node.term_id,
        property: node.label || String(node.term_id || '').split(':').pop(),
        prefix: node.ontology_prefix || '',
        kind: String(node.source || '').includes('datatype') ? 'DatatypeProperty' : 'ObjectProperty',
        domain: 'Not declared',
        range: 'Not declared',
        axiomCount: 0,
      }));
  }, [edgeRows, reasoningPropertyRows, visibleNodes]);

  const selectedPropertyRow = useMemo(() => {
    if (!selectedTerm) return null;
    return objectPropertyRows.find((row) => row.id === selectedTerm.term_id) || null;
  }, [objectPropertyRows, selectedTerm]);

  const selectedAxioms = useMemo(() => {
    if (!selectedTerm) return [];
    return edgeRows.filter((edge) => edge.sourceId === selectedTerm.term_id || edge.targetId === selectedTerm.term_id);
  }, [edgeRows, selectedTerm]);

  const activeEmptyLabel = tableMode === 'properties'
    ? 'No object or datatype properties were resolved for this ontology.'
    : tableMode === 'axioms'
      ? 'No OWL axioms are available for this ontology slice.'
      : 'No ontology classes are available for this ontology slice.';

  const treeColumns = useMemo(() => [
    {
      headerName: 'Class Hierarchy',
      field: 'label',
      flex: 1,
      minWidth: 220,
      tooltipField: 'path',
      cellStyle: { ...gridTextCell, display: 'flex', alignItems: 'center' },
      cellRenderer: (params) => (
        <button
          type="button"
          onClick={() => setSelectedTermId(params.data.termId)}
          style={{
            border: 'none',
            background: 'transparent',
            color: selectedTerm?.term_id === params.data.termId ? C.primary : C.textPrimary,
            fontWeight: selectedTerm?.term_id === params.data.termId ? 800 : 600,
            cursor: 'pointer',
            textAlign: 'left',
            width: '100%',
            padding: 0,
            minWidth: 0,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            paddingLeft: `${Math.min(params.data.depth || 0, 8) * 16}px`,
          }}
          title={params.data.termId}
        >
          <span
            style={{
              width: 16,
              minWidth: 16,
              height: 16,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              borderRadius: 999,
              background: (params.data.depth || 0) > 0 ? C.primaryLight : C.bg,
              color: (params.data.depth || 0) > 0 ? C.primary : C.textMuted,
              fontSize: 10,
              fontWeight: 800,
            }}
          >
            {(params.data.depth || 0) > 0 ? '|' : 'R'}
          </span>
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{params.value}</span>
        </button>
      ),
    },
    { headerName: 'Children', field: 'children', width: 92, type: 'numericColumn' },
  ], [selectedTerm, gridTextCell]);

  const classColumns = useMemo(() => [
    {
      headerName: 'Class',
      field: 'label',
      pinned: 'left',
      flex: 1.2,
      minWidth: 240,
      tooltipField: 'termId',
      cellStyle: { ...gridTextCell, display: 'flex', alignItems: 'center' },
      cellRenderer: (params) => (
        <button type="button" onClick={() => setSelectedTermId(params.data.termId)} style={{ border: 'none', background: 'transparent', color: C.primary, fontWeight: 700, cursor: 'pointer', padding: 0, minWidth: 0, maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {params.value}
        </button>
      ),
    },
    { headerName: 'Parents', field: 'parents', flex: 1, minWidth: 148, tooltipField: 'parents', cellStyle: gridTextCell },
    { headerName: 'Children', field: 'children', width: 92, type: 'numericColumn', cellStyle: gridTextCell },
    { headerName: 'Prefix', field: 'prefix', width: 102, cellStyle: gridTextCell },
  ], [gridTextCell]);

  const propertyColumns = useMemo(() => [
    { headerName: 'Property', field: 'property', pinned: 'left', flex: 1.2, minWidth: 230, tooltipField: 'id', cellStyle: gridTextCell },
    { headerName: 'Kind', field: 'kind', width: 124, cellStyle: gridTextCell },
    { headerName: 'Domain', field: 'domain', flex: 1, minWidth: 148, tooltipField: 'domain', cellStyle: gridTextCell },
    { headerName: 'Range', field: 'range', flex: 1, minWidth: 148, tooltipField: 'range', cellStyle: gridTextCell },
    { headerName: 'Axioms', field: 'axiomCount', width: 88, type: 'numericColumn', cellStyle: gridTextCell },
  ], [gridTextCell]);

  const axiomColumns = useMemo(() => [
    { headerName: 'Source', field: 'source', pinned: 'left', flex: 1.1, minWidth: 210, tooltipField: 'sourceId', cellStyle: gridTextCell },
    { headerName: 'Axiom', field: 'axiom', width: 124, cellStyle: gridTextCell },
    { headerName: 'Target', field: 'target', flex: 1, minWidth: 152, tooltipField: 'targetId', cellStyle: gridTextCell },
    { headerName: 'Prefix', field: 'prefix', width: 96, cellStyle: gridTextCell },
  ], [gridTextCell]);

  const activeRows = tableMode === 'properties' ? objectPropertyRows : tableMode === 'axioms' ? edgeRows : classRows;
  const activeColumns = tableMode === 'properties' ? propertyColumns : tableMode === 'axioms' ? axiomColumns : classColumns;
  const activeTitle = tableMode === 'properties'
    ? `Object/Data Properties (${objectPropertyRows.length})`
    : tableMode === 'axioms'
      ? `OWL Axioms (${edgeRows.length})`
      : `Classes (${classRows.length})`;

  const browserStats = [
    { label: 'Classes', value: hierarchy.rows.length },
    { label: 'Properties', value: objectPropertyRows.length },
    { label: 'Axioms', value: edgeRows.length },
    { label: 'Terms', value: visibleNodes.length },
  ];

  const handleOntologyRowSelection = useCallback((row) => {
    if (!row) return;
    if (tableMode === 'properties' && row.id) {
      setSelectedTermId(row.id);
      return;
    }
    if (tableMode === 'axioms') {
      setSelectedTermId(row.sourceId || row.targetId || '');
      return;
    }
    if (row.termId) {
      setSelectedTermId(row.termId);
      return;
    }
    if (row.id) {
      setSelectedTermId(row.id);
    }
  }, [tableMode]);

  return (
    <div style={{ display: 'grid', gap: 12, minHeight: 680 }}>
      <section style={{ border: `1px solid ${C.border}`, borderRadius: 8, background: C.surface, padding: '12px 14px', display: 'grid', gap: 10 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', gap: 12, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: C.textPrimary }}>OWL Browser</div>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(88px, 1fr))', gap: 8, minWidth: 'min(100%, 420px)' }}>
            {browserStats.map((stat) => (
              <div key={stat.label} style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: '8px 10px' }}>
                <div style={{ fontSize: 10, fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>{stat.label}</div>
                <div style={{ fontSize: 18, fontWeight: 800, color: C.primary, marginTop: 2 }}>{stat.value}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <div className="owl-browser-layout" style={{ display: 'grid', gridTemplateColumns: 'minmax(280px, 0.95fr) minmax(520px, 1.9fr) minmax(300px, 1fr)', gap: 12, minHeight: 620, alignItems: 'start' }}>
        <section style={{ minWidth: 0, border: `1px solid ${C.border}`, borderRadius: 8, background: C.surface, overflow: 'hidden' }}>
          <div style={{ padding: '10px 12px', borderBottom: `1px solid ${C.border}` }}>
            <div style={{ fontSize: 13, fontWeight: 800, color: C.textPrimary }}>Hierarchy</div>
          </div>
          <div style={{ padding: 10 }}>
            <DataGridWidget
              title={`Class Hierarchy (${hierarchy.rows.length})`}
              subtitle="Browse ontology depth and select a focal term."
              rows={hierarchy.rows}
              columns={treeColumns}
              height={566}
              minGridHeight={566}
              paginationPageSize={20}
              emptyLabel="No class hierarchy available"
            />
          </div>
        </section>

        <section style={{ minWidth: 0, border: `1px solid ${C.border}`, borderRadius: 8, background: C.surface, overflow: 'hidden', display: 'grid', gridTemplateRows: 'auto 1fr' }}>
          <div style={{ padding: '10px 12px', borderBottom: `1px solid ${C.border}`, display: 'grid', gap: 10 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'start', flexWrap: 'wrap' }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 800, color: C.textPrimary }}>Semantic Tables</div>
              </div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
                {[
                  { id: 'classes', label: 'Classes' },
                  { id: 'properties', label: 'Properties' },
                  { id: 'axioms', label: 'Axioms' },
                ].map((mode) => (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => setTableMode(mode.id)}
                    style={{
                      border: `1px solid ${tableMode === mode.id ? C.primary : C.borderDark}`,
                      background: tableMode === mode.id ? C.primary : C.surface,
                      color: tableMode === mode.id ? '#fff' : C.textPrimary,
                      borderRadius: 6,
                      padding: '6px 12px',
                      fontSize: 12,
                      fontWeight: 800,
                      cursor: 'pointer',
                    }}
                  >
                    {mode.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div style={{ padding: 10, minWidth: 0 }}>
            <DataGridWidget
              title={activeTitle}
              subtitle={tableMode === 'properties' ? 'Domain, range, and property semantics' : tableMode === 'axioms' ? 'Resolved relationships and OWL expressions' : 'Classes with parent and child coverage'}
              rows={activeRows}
              columns={activeColumns}
              height={566}
              minGridHeight={566}
              paginationPageSize={20}
              emptyLabel={activeEmptyLabel}
              onRowClicked={handleOntologyRowSelection}
            />
          </div>
        </section>

        <aside style={{ border: `1px solid ${C.border}`, borderRadius: 8, background: C.surface, minWidth: 0, overflow: 'hidden', maxHeight: 696, display: 'grid', gridTemplateRows: 'auto 1fr' }}>
          <div style={{ padding: '10px 12px', borderBottom: `1px solid ${C.border}`, display: 'flex', justifyContent: 'space-between', gap: 8 }}>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: C.textPrimary }}>Inspector</div>
              <div style={{ fontSize: 11, color: C.textSec, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {reasoning?.engine === 'owlready2' ? 'Owlready2 semantics' : 'Ontology metadata'}
              </div>
            </div>
            {selectedTerm?.ontology_prefix && (
              <span style={{ alignSelf: 'start', background: C.primaryLight, color: C.primary, border: `1px solid ${C.border}`, borderRadius: 999, padding: '2px 8px', fontSize: 11, fontWeight: 800, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {selectedTerm.ontology_prefix}
              </span>
            )}
          </div>
          {selectedTerm ? (
            <div style={{ padding: 12, display: 'grid', gap: 12, overflow: 'auto' }}>
              <section style={{ display: 'grid', gap: 6 }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: C.primary, wordBreak: 'break-word' }}>
                  {selectedTerm.label || String(selectedTerm.term_id).split(':').pop()}
                </div>
                <code style={{ display: 'block', fontSize: 11, color: C.textSec, wordBreak: 'break-all' }}>{selectedTerm.term_id}</code>
              </section>

              <section style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: 8 }}>
                  <div style={{ fontSize: 10, fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>Parents</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: C.textPrimary }}>{hierarchy.parentByChild.get(selectedTerm.term_id)?.length || 0}</div>
                </div>
                <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: 8 }}>
                  <div style={{ fontSize: 10, fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>Children</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: C.textPrimary }}>{hierarchy.childrenByParent.get(selectedTerm.term_id)?.length || 0}</div>
                </div>
              </section>

              {(selectedTerm.definition || selectedTerm.comment) && (
                <section style={{ display: 'grid', gap: 6 }}>
                  <div style={{ fontSize: 11, fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Description</div>
                  <div style={{ fontSize: 12, color: C.textPrimary, lineHeight: 1.5, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: 10 }}>
                    {selectedTerm.definition || selectedTerm.comment}
                  </div>
                </section>
              )}

              {selectedPropertyRow && (
                <section style={{ display: 'grid', gap: 8 }}>
                  <div style={{ fontSize: 11, fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Property Semantics</div>
                  <div style={{ display: 'grid', gap: 8 }}>
                    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: 8 }}>
                      <div style={{ fontSize: 10, fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>Kind</div>
                      <div style={{ fontSize: 13, fontWeight: 700, color: C.textPrimary, marginTop: 4 }}>{selectedPropertyRow.kind}</div>
                    </div>
                    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: 8 }}>
                      <div style={{ fontSize: 10, fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>Domain</div>
                      <div style={{ fontSize: 12, color: C.textPrimary, marginTop: 4, lineHeight: 1.45, wordBreak: 'break-word' }}>{selectedPropertyRow.domain}</div>
                    </div>
                    <div style={{ background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: 8 }}>
                      <div style={{ fontSize: 10, fontWeight: 800, color: C.textMuted, textTransform: 'uppercase' }}>Range</div>
                      <div style={{ fontSize: 12, color: C.textPrimary, marginTop: 4, lineHeight: 1.45, wordBreak: 'break-word' }}>{selectedPropertyRow.range}</div>
                    </div>
                  </div>
                </section>
              )}

              <section style={{ display: 'grid', gap: 6 }}>
                <div style={{ fontSize: 11, fontWeight: 800, color: C.textSec, textTransform: 'uppercase' }}>Related Axioms</div>
                <div style={{ display: 'grid', gap: 6, maxHeight: 280, overflow: 'auto' }}>
                  {selectedAxioms.length === 0 ? (
                    <div style={{ fontSize: 12, color: C.textMuted, background: C.bg, border: `1px solid ${C.border}`, borderRadius: 6, padding: 10 }}>
                      No axioms found for selected term.
                    </div>
                  ) : selectedAxioms.slice(0, 30).map((edge) => (
                    <div key={edge.id} style={{ border: `1px solid ${C.border}`, borderRadius: 6, padding: 8, background: C.bg }}>
                      <RelBadge type={edge.axiom} />
                      <div style={{ fontSize: 12, color: C.textPrimary, marginTop: 5, lineHeight: 1.4, wordBreak: 'break-word' }}>
                        {edge.source} -> {edge.target}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            </div>
          ) : (
            <div style={{ padding: 24, color: C.textMuted, fontSize: 12 }}>
              Select a class, property, or axiom row to inspect details.
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function buildFallbackDictionaryFromTaxonomy(taxonomyPayload, prefixHint = '') {
  const taxonomyNodes = taxonomyPayload?.nodes || [];
  const entities = Object.fromEntries(
    taxonomyNodes.map((node) => {
      const key = node.label || node.term_id?.split(':').pop() || node.term_id;
      return [key, {
        id: node.term_id,
        label: node.label || key,
        definition: node.definition || '',
        ontology_prefix: node.ontology_prefix || prefixHint,
      }];
    })
  );

  return {
    entities,
    relationships: {},
    properties: {},
    _source: 'taxonomy_fallback',
  };
}

const BRIDGE_SOURCE_KINDS = ['Entity', 'Attribute', 'Relationship', 'Metadata'];
const BRIDGE_TARGET_KINDS = ['Class', 'ObjectProperty', 'DatatypeProperty', 'AnnotationProperty'];

function normalizeBridgeLabel(value) {
  return String(value || '').trim();
}

function uniqueBridgeOptions(options = []) {
  const seen = new Set();
  const result = [];
  options.forEach((option) => {
    if (!option || typeof option !== 'object') return;
    const value = normalizeBridgeLabel(option.value);
    if (!value) return;
    const key = value.toLowerCase();
    if (seen.has(key)) return;
    seen.add(key);
    result.push({
      value,
      label: normalizeBridgeLabel(option.label) || value,
      subtitle: normalizeBridgeLabel(option.subtitle),
      kind: normalizeBridgeLabel(option.kind),
      origin: normalizeBridgeLabel(option.origin),
    });
  });
  return result;
}

function inferBridgeSourceKind(row = {}) {
  const keys = Object.keys(row || {}).map((key) => String(key).toLowerCase());
  const valueSet = new Set(
    ['entity_type', 'element_type', 'type', 'xsi:type', 'class', 'category', 'part_type', 'name']
      .map((key) => normalizeBridgeLabel(row[key]).toLowerCase())
      .filter(Boolean),
  );
  const relationshipMarkers = ['ref', 'refs', 'href', 'idref', 'instance', 'related', 'source', 'target', 'parent', 'child'];
  const metadataMarkers = ['filename', 'workflow_id', 'namespace', 'ontology_prefix', 'ontology_name', 'source_ontology', 'manifest', 'provenance'];
  const attributeMarkers = ['value', 'text', 'description', 'comment', 'label', 'datatype', 'attribute'];

  if (keys.some((key) => relationshipMarkers.some((marker) => key.includes(marker)))) return 'Relationship';
  if (keys.some((key) => metadataMarkers.some((marker) => key.includes(marker)))) return 'Metadata';
  if (keys.some((key) => attributeMarkers.some((marker) => key.includes(marker)))) return 'Attribute';
  if (valueSet.has('relationship') || valueSet.has('edge') || valueSet.has('link')) return 'Relationship';
  if (valueSet.has('attribute') || valueSet.has('datatype') || valueSet.has('property')) return 'Attribute';
  return 'Entity';
}

function collectBridgeSourceOptions(preview = {}, kind = 'Entity') {
  const rows = Array.isArray(preview.sample_rows) ? preview.sample_rows : [];
  const columns = Array.isArray(preview.columns) ? preview.columns : [];
  const options = [];
  const add = (value, label, subtitle = '', origin = 'preview') => {
    const normalizedValue = normalizeBridgeLabel(value);
    if (!normalizedValue) return;
    options.push({ value: normalizedValue, label: normalizeBridgeLabel(label) || normalizedValue, subtitle, kind, origin });
  };

  const entityTypeKeys = ['entity_type', 'element_type', 'type', 'xsi:type', 'class', 'category', 'part_type'];
  const entityValueKeys = ['part_number', 'partno', 'item_id', 'itemid', 'number', 'name', 'title', 'display_name', 'part_name', 'instance_name', 'external_id', 'id', 'uid', 'instance_id', 'import_row_key'];
  const relationshipTokens = ['relationship', 'ref', 'href', 'link', 'source', 'target', 'parent', 'child', 'masterref', 'generalref', 'relatedref'];
  const metadataTokens = ['filename', 'workflow', 'namespace', 'ontology', 'source_format', 'source_ontology', 'import_id', 'manifest', 'provenance', 'file_type'];
  const hasToken = (value, tokens) => tokens.some((token) => String(value || '').toLowerCase().includes(token));

  if (kind === 'Entity') {
    rows.forEach((row) => {
      if (!row || typeof row !== 'object') return;
      if (inferBridgeSourceKind(row) === 'Relationship') return;
      const keys = Object.keys(row);
      const valueKey = keys.find((key) => entityValueKeys.includes(String(key).toLowerCase()));
      const typeKey = keys.find((key) => entityTypeKeys.includes(String(key).toLowerCase()));
      const fallbackKey = keys.find((key) => !hasToken(key, metadataTokens) && !hasToken(key, relationshipTokens));
      const chosenKey = valueKey || fallbackKey;
      const value = chosenKey ? row[chosenKey] : '';
      const entityType = typeKey ? row[typeKey] : '';
      if (!normalizeBridgeLabel(value)) return;
      add(value, value, entityType ? `Instance ${entityType}` : 'Instance entity', chosenKey || 'preview');
    });
  }

  if (kind === 'Attribute') {
    columns.forEach((column) => {
      const lower = String(column || '').toLowerCase();
      if (!lower) return;
      if (entityTypeKeys.includes(lower) || hasToken(lower, relationshipTokens) || hasToken(lower, metadataTokens)) return;
      add(column, column, 'Instance attribute field', 'column');
    });
  }

  if (kind === 'Relationship') {
    columns.forEach((column) => {
      const lower = String(column || '').toLowerCase();
      if (hasToken(lower, relationshipTokens)) {
        add(column, column, 'Instance relationship field', 'column');
      }
    });
    rows.forEach((row) => {
      if (!row || typeof row !== 'object') return;
      ['relationship_type', 'ref_type', 'reference_type', 'type'].forEach((key) => {
        if (row[key]) add(row[key], row[key], 'Relationship type value', key);
      });
    });
  }

  if (kind === 'Metadata') {
    columns.forEach((column) => {
      const lower = String(column || '').toLowerCase();
      if (hasToken(lower, metadataTokens)) {
        add(column, column, 'Import metadata field', 'column');
      }
    });
    ['filename', 'workflow_id', 'namespace', 'ontology_prefix', 'ontology_name', 'source_ontology', 'source_format', 'import_id', 'file_type']
      .forEach((key) => add(key, key, 'Import metadata field', 'metadata'));
  }

  return uniqueBridgeOptions(options).slice(0, 120);
}

function collectBridgeTargetOptions(reasoning = {}, kind = 'Class') {
  const byKind = {
    Class: reasoning?.classes || [],
    ObjectProperty: reasoning?.object_properties || [],
    DatatypeProperty: reasoning?.datatype_properties || [],
    AnnotationProperty: reasoning?.annotation_properties || [],
  };
  const rows = byKind[kind] || [];
  return uniqueBridgeOptions(rows.map((row) => {
    const label = row?.label || row?.name || row?.term_id || row?.iri || row?.uri;
    const domain = Array.isArray(row?.domain) ? row.domain.map((item) => item?.label || item?.iri || '').filter(Boolean).slice(0, 2).join(', ') : '';
    const range = Array.isArray(row?.range) ? row.range.map((item) => item?.label || item?.iri || '').filter(Boolean).slice(0, 2).join(', ') : '';
    const subtitle = kind === 'Class' ? 'Ontology class' : [domain ? `domain ${domain}` : '', range ? `range ${range}` : ''].filter(Boolean).join(' | ');
    return { value: label, label, subtitle, kind, origin: 'reasoning' };
  })).slice(0, 160);
}

function normalizeMappingTypeLabel(value) {
  const raw = String(value || '').trim();
  if (!raw) return 'suggested';
  return raw;
}

function normalizeBridgeMappingRow(row = {}) {
  const sourceTerm = normalizeBridgeLabel(row.source_term || row.sourceField || row.import_row_key || row.source_label || row.source_instance_id || 'instance');
  const targetTerm = normalizeBridgeLabel(row.target_term || row.targetOntologyIRI || row.ontology_class_element_id || row.ontology_term || 'ontology');
  const validationStatus = normalizeBridgeLabel(row.validation_status || row.validationStatus || (row.selected_for_apply || row.approvedByUser ? 'approved' : 'needs_review'));
  const mappingType = normalizeMappingTypeLabel(row.mapping_type || row.mappingType || (row.selected_for_apply ? 'autoMap' : 'suggested'));
  const confidence = Number.isFinite(Number(row.confidenceScore ?? row.confidence)) ? Number(row.confidenceScore ?? row.confidence) : 0;
  return {
    source_instance_id: row.source_instance_id || row.sourceInstanceId || 'instance',
    source_instance_label: row.source_instance_label || row.sourceInstanceLabel || 'Imported instance',
    source_term: sourceTerm,
    source_label: normalizeBridgeLabel(row.source_label || row.sourceLabel || sourceTerm),
    source_type: normalizeBridgeLabel(row.source_type || row.sourceType || 'Entity'),
    target_term: targetTerm,
    target_label: normalizeBridgeLabel(row.target_label || row.targetLabel || targetTerm),
    target_ontology_type: normalizeBridgeLabel(row.target_ontology_type || row.targetOntologyType || 'Class'),
    mapping_type: mappingType,
    confidence,
    evidence: Array.isArray(row.evidence) ? row.evidence : [],
    signal_type: normalizeBridgeLabel(row.signal_type || row.signalType || ''),
    ambiguous: Boolean(row.ambiguous),
    selected_for_apply: Boolean(row.selected_for_apply || row.approvedByUser || validationStatus === 'approved' || validationStatus === 'auto_approved'),
    validation_status: validationStatus,
    approvedByUser: Boolean(row.approvedByUser || row.selected_for_apply || validationStatus === 'approved' || validationStatus === 'auto_approved'),
    userComment: normalizeBridgeLabel(row.userComment || row.user_comment),
  };
}

// ── Main component ─────────────────────────────────────────────────────────────
export default function OntologyMapper() {
  const [data, setData] = useState({ nodes: [], edges: [] });
  const [mappingEdges, setMappingEdges] = useState([]);
  const [vocabEdges, setVocabEdges] = useState([]);
  const [taxonomy, setTaxonomy] = useState(null);
  const [reasoning, setReasoning] = useState(null);
  const [targetOntologyDictionary, setTargetOntologyDictionary] = useState({ entities: {}, relationships: {}, properties: {} });
  const [dictionarySourceMode, setDictionarySourceMode] = useState('primary');
  const [targetDictionarySourceMode, setTargetDictionarySourceMode] = useState('primary');
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedMapping, setSelectedMapping] = useState('');
  const [selectedMappingType, setSelectedMappingType] = useState('');
  const [selectedOntologyApi, setSelectedOntologyApi] = useState('');
  const [activeView, setActiveView] = useState('dictionary');
  const [filter, setFilter] = useState('');
  const [prefixFilter, setPrefixFilter] = useState(null);
  const [mappingOptions, setMappingOptions] = useState([]);
  const [mappingOptionsError, setMappingOptionsError] = useState(null);
  const [, setOntologyDictionary] = useState({ entities: {}, relationships: {}, properties: {} });
  const [mapBusy, setMapBusy] = useState(false);
  const [mapMessage, setMapMessage] = useState(null);
  const [importTasks, setImportTasks] = useState([]);
  const [selectedImportTaskId, setSelectedImportTaskId] = useState('');
  const [importTasksLoading, setImportTasksLoading] = useState(false);
  const [importTasksError, setImportTasksError] = useState(null);
  const [selectedImportTaskDetails, setSelectedImportTaskDetails] = useState(null);
  const [selectedImportTaskPreview, setSelectedImportTaskPreview] = useState(null);
  const [unifyBusy, setUnifyBusy] = useState(false);
  const [unifyResult, setUnifyResult] = useState(null);
  const [bridgeCandidates, setBridgeCandidates] = useState([]);
  const [selectedMappingEdgeIndex, setSelectedMappingEdgeIndex] = useState(-1);
  const [bridgeSourceKind, setBridgeSourceKind] = useState('Entity');
  const [bridgeSourceTerm, setBridgeSourceTerm] = useState('');
  const [bridgeTargetKind, setBridgeTargetKind] = useState('Class');
  const [bridgeTargetTerm, setBridgeTargetTerm] = useState('');
  const [bridgeComment, setBridgeComment] = useState('');
  const [bridgeApproved, setBridgeApproved] = useState(false);
  const [mergeSourceOntologyId, setMergeSourceOntologyId] = useState('');
  const [mergeBusy, setMergeBusy] = useState(false);
  const [mergeResult, setMergeResult] = useState(null);
  const selectedImportTask = useMemo(
    () => importTasks.find((task) => task.task_id === selectedImportTaskId) || null,
    [importTasks, selectedImportTaskId],
  );
  const selectedImportTaskInfo = selectedImportTaskDetails || selectedImportTask;
  const selectedOntologyOption = useMemo(
    () => (
      mappingOptions.find((option) => option.value === selectedMapping)
      || mappingOptions.find((option) => option.prefix === selectedOntologyApi || option.value === selectedOntologyApi)
      || null
    ),
    [mappingOptions, selectedMapping, selectedOntologyApi],
  );
  const applyOntologySelection = useCallback((rawValue) => {
    if (!rawValue) {
      setSelectedMapping('');
      setSelectedOntologyApi('');
      return null;
    }

    const selectedOption = mappingOptions.find(
      (option) => option.value === rawValue || option.prefix === rawValue || option.ontologyKey === rawValue,
    );

    if (!selectedOption) {
      setSelectedMapping(rawValue);
      setSelectedOntologyApi(rawValue);
      return null;
    }

    const nextValue = selectedOption.value || rawValue;
    const nextApi = selectedOption.prefix || selectedOption.ontologyKey || selectedOption.value || rawValue;
    setSelectedMapping(nextValue);
    setSelectedOntologyApi(nextApi);
    if (selectedOption.type) {
      setSelectedMappingType(selectedOption.type);
    }
    return selectedOption;
  }, [mappingOptions]);
  const selectedImportManifest = selectedImportTask?.artifact_manifest || selectedImportTask?.artifactManifest || null;
  const selectedBridgeSummary = unifyResult?.summary || null;
  const visibleMappingEdges = useMemo(() => {
    const baseEdges = (mappingEdges || [])
      .filter((edge) => String(edge.mapping_type || '').toLowerCase() !== 'property_of')
      .map((edge) => normalizeBridgeMappingRow(edge));
    if (baseEdges.length > 0) return baseEdges;
    return (bridgeCandidates || [])
      .filter(Boolean)
      .map((candidate) => normalizeBridgeMappingRow({
        source_instance_id: selectedImportTaskId || candidate.source_instance_id || 'instance',
        source_instance_label: selectedImportTask?.filename || candidate.source_instance_label || 'Imported instance',
        source_term: candidate.import_row_key || candidate.source_term || candidate.source_label || selectedImportTaskId || 'instance',
        source_label: candidate.source_label || candidate.import_row_key || candidate.source_term || selectedImportTask?.filename || 'Imported entity',
        source_type: candidate.source_type || 'Entity',
        target_term: candidate.ontology_class_element_id || candidate.ontology_term || selectedOntologyApi || 'ontology',
        target_label: candidate.ontology_term || selectedOntologyOption?.label || candidate.ontology_class_element_id || 'Ontology class',
        target_ontology_type: candidate.target_ontology_type || 'Class',
        mapping_type: candidate.selected_for_apply ? 'autoMap' : (candidate.validation_status || 'suggested'),
        confidence: candidate.confidence,
        evidence: candidate.evidence || [],
        signal_type: candidate.signal_type || 'metadata',
        ambiguous: candidate.ambiguous,
        selected_for_apply: candidate.selected_for_apply,
        validation_status: candidate.validation_status,
        user_comment: candidate.user_comment,
      }));
  }, [bridgeCandidates, mappingEdges, selectedOntologyApi, selectedImportTaskId, selectedImportTask, selectedOntologyOption]);
  const selectedMappingEdge = useMemo(() => {
    if (selectedMappingEdgeIndex < 0) return null;
    return visibleMappingEdges[selectedMappingEdgeIndex] || null;
  }, [visibleMappingEdges, selectedMappingEdgeIndex]);

  const sourceOptionsByKind = useMemo(() => {
    const preview = selectedImportTaskPreview || selectedImportTaskInfo?.preview_data || selectedImportTaskInfo?.previewData || {};
    return {
      Entity: collectBridgeSourceOptions(preview, 'Entity'),
      Attribute: collectBridgeSourceOptions(preview, 'Attribute'),
      Relationship: collectBridgeSourceOptions(preview, 'Relationship'),
      Metadata: collectBridgeSourceOptions(preview, 'Metadata'),
    };
  }, [selectedImportTaskPreview, selectedImportTaskInfo]);

  const targetOptionsByKind = useMemo(() => ({
    Class: collectBridgeTargetOptions(reasoning, 'Class'),
    ObjectProperty: collectBridgeTargetOptions(reasoning, 'ObjectProperty'),
    DatatypeProperty: collectBridgeTargetOptions(reasoning, 'DatatypeProperty'),
    AnnotationProperty: collectBridgeTargetOptions(reasoning, 'AnnotationProperty'),
  }), [reasoning]);

  const sourceEntityOptions = useMemo(() => sourceOptionsByKind[bridgeSourceKind] || [], [sourceOptionsByKind, bridgeSourceKind]);
  const targetEntityOptions = useMemo(() => {
    const fromReasoning = targetOptionsByKind[bridgeTargetKind] || [];
    if (fromReasoning.length > 0) return fromReasoning;
    const fallbackDictionary = {
      Class: Object.keys(targetOntologyDictionary.entities || {}).sort().map((value) => ({ value, label: value, subtitle: 'Ontology class', kind: 'Class', origin: 'dictionary' })),
      ObjectProperty: Object.keys(targetOntologyDictionary.relationships || {}).sort().map((value) => ({ value, label: value, subtitle: 'Ontology object property', kind: 'ObjectProperty', origin: 'dictionary' })),
      DatatypeProperty: Object.keys(targetOntologyDictionary.properties || {}).sort().map((value) => ({ value, label: value, subtitle: 'Ontology datatype property', kind: 'DatatypeProperty', origin: 'dictionary' })),
      AnnotationProperty: [],
    };
    return fallbackDictionary[bridgeTargetKind] || [];
  }, [targetOptionsByKind, bridgeTargetKind, targetOntologyDictionary]);
  const mergeSourceOptions = useMemo(
    () => mappingOptions.filter((option) => option?.value && option.value !== selectedMapping),
    [mappingOptions, selectedMapping],
  );

  const normalizeSourceFormat = (rawType, ontologyId) => {
    const valid = new Set(['plmxml', 'step', 'xmi', 'xml']);
    const t = String(rawType || '').toLowerCase();
    if (valid.has(t)) return t;

    const id = String(ontologyId || '').toLowerCase();
    if (id.startsWith('auto-')) {
      const autoType = id.replace('auto-', '');
      if (valid.has(autoType)) return autoType;
    }

    const firstToken = id.split('_')[0];
    if (valid.has(firstToken)) return firstToken;

    return 'plmxml';
  };

  const buildOntologyOptions = useCallback((ontologies = []) => {
    const allOptions = ontologies.map(ont => ({
      value: ont.ontology_id || ont.id,
      type: normalizeSourceFormat(ont.file_type || ont.type, ont.ontology_id || ont.id),
      ontologyKey: ont.prefix || '',
      label: `${ont.ontology_name || ont.name || ont.ontology_id} [${ont.prefix || ''}]`,
      prefix: ont.prefix || '',
      uploaded_at: ont.uploaded_at || '',
      source: ont.source,
      usageCount: ont.usageCount,
    }));

    // Deduplicate by ontology prefix and keep the newest upload.
    const byPrefix = new Map();
    allOptions.forEach((o) => {
      if (!byPrefix.has(o.prefix) || o.uploaded_at > byPrefix.get(o.prefix).uploaded_at) {
        byPrefix.set(o.prefix, o);
      }
    });
    return Array.from(byPrefix.values());
  }, []);

  const parseLegacyMappingKey = (key = '') => {
    const value = String(key);
    const tokens = value.split('_').filter(Boolean);
    if (tokens.length >= 3) {
      return {
        source: tokens[0],
        mappingType: tokens[tokens.length - 2],
        targetFromKey: tokens[tokens.length - 1],
      };
    }
    return {
      source: value,
      mappingType: 'mapsTo',
      targetFromKey: '',
    };
  };

  const resolveSelectedOntologyOption = useCallback((options, selectedValue) => {
    if (!Array.isArray(options) || options.length === 0) return null;
    const selected = options.find((o) => o.value === selectedValue);
    return selected || options[0] || null;
  }, []);

  // Get ontology options from centralized context (shared across all components)
  const { ontologies: contextOntologies } = useOntologies();

  useEffect(() => {
    // Load available mapping options from centralized context
    // Important: do NOT overwrite Alignment source/target selections on unrelated state changes.
    try {
      setMappingOptionsError(null);
      const options = buildOntologyOptions(contextOntologies || []);
      setMappingOptions(options);

      if (options.length === 0) {
        setMappingOptionsError('No ontologies available. Please upload an ontology first.');
        setLoading(false);
        return;
      }

      // Initialize defaults only once (or if current selection no longer exists)
      const selectedOption = resolveSelectedOntologyOption(options, selectedMapping);
      if (!selectedOption) {
        setLoading(false);
        return;
      }

      const selectedOntologyKey = selectedOption.prefix || selectedOption.ontologyKey || selectedOption.value || '';
      if (selectedOption.value !== selectedMapping || selectedOntologyApi !== selectedOntologyKey) {
        applyOntologySelection(selectedOption.value);
      }

      if (!selectedMappingType) {
        setSelectedMappingType(selectedOption.type);
      }

    } catch (e) {
      const errorMsg = e.message || 'Failed to process ontologies';
      setMappingOptionsError(errorMsg);
      setLoading(false);
      console.warn('Failed to process ontologies:', e);
    }
  }, [applyOntologySelection, contextOntologies, buildOntologyOptions, resolveSelectedOntologyOption, selectedMapping, selectedMappingType, selectedOntologyApi]);

  useEffect(() => {
    if (!selectedMappingType) {
      setSelectedMappingType(SOURCE_FORMATS[0].id);
    }
  }, [selectedMappingType]);

  useEffect(() => {
    let cancelled = false;
    const loadImportTasks = async () => {
      setImportTasksLoading(true);
      setImportTasksError(null);
      try {
        const res = await API_METHODS.import.getTasks();
        const tasks = (res.data && res.data.tasks) || [];
        if (cancelled) return;
        setImportTasks(tasks);
        if (!selectedImportTaskId && tasks.length > 0) {
          setSelectedImportTaskId(tasks[0].task_id || '');
        }
      } catch (e) {
        if (!cancelled) {
          setImportTasksError(e?.response?.data?.detail || e.message || 'Failed to load instance tasks.');
        }
      } finally {
        if (!cancelled) {
          setImportTasksLoading(false);
        }
      }
    };
    loadImportTasks();
    return () => {
      cancelled = true;
    };
  }, [selectedImportTaskId]);

  useEffect(() => {
    if (!selectedImportTaskId) return;
    const task = importTasks.find((item) => item.task_id === selectedImportTaskId);
    const normalized = normalizeSourceFormat(task?.file_type || task?.source_format || '', task?.task_id || selectedImportTaskId);
    if (normalized && normalized !== selectedMappingType) {
      setSelectedMappingType(normalized);
    }
  }, [selectedImportTaskId, importTasks, selectedMappingType]);

  useEffect(() => {
    let cancelled = false;
    const loadSelectedImportDetails = async () => {
      if (!selectedImportTaskId) {
        setSelectedImportTaskDetails(null);
        setSelectedImportTaskPreview(null);
        return;
      }
      try {
        const [statusRes, previewRes] = await Promise.allSettled([
          API_METHODS.import.getStatus(selectedImportTaskId),
          API_METHODS.import.getPreview(selectedImportTaskId),
        ]);
        if (cancelled) return;
        setSelectedImportTaskDetails(statusRes.status === 'fulfilled' ? (statusRes.value?.data || null) : null);
        setSelectedImportTaskPreview(previewRes.status === 'fulfilled' ? (previewRes.value?.data || null) : null);
      } catch (_err) {
        if (!cancelled) {
          setSelectedImportTaskDetails(null);
          setSelectedImportTaskPreview(null);
        }
      }
    };
    loadSelectedImportDetails();
    return () => {
      cancelled = true;
    };
  }, [selectedImportTaskId]);

  useEffect(() => {
    if (!selectedOntologyApi || !selectedMappingType) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    // Load data dictionary and vocabulary for selected mapping
    const loadMappingData = async () => {
      if (!cancelled) {
        setLoading(true);
        setError(null);
      }
      try {
        // Use selectedOntologyApi (the currently selected uploaded ontology prefix).
        // The backend now supports any prefix via generic /{prefix}/data-dictionary routes.
        const [dictRes, mapRes, taxonomyRes, reasoningRes] = await Promise.allSettled([
          API_METHODS.ontology.getDataDictionary(selectedOntologyApi),
          API_METHODS.ontology.getMappings(selectedOntologyApi, selectedMappingType),
          API_METHODS.ontology.getTaxonomy(selectedOntologyApi),
          API_METHODS.ontology.getReasoning(selectedOntologyApi),
        ]);

        const taxonomyData = taxonomyRes.status === 'fulfilled' ? taxonomyRes.value.data : null;
        const reasoningData = reasoningRes.status === 'fulfilled' ? reasoningRes.value.data : null;
        const dictDataRaw = (dictRes.status === 'fulfilled' ? dictRes.value.data.data : null) || {};
        const usingFallbackDictionary = Object.keys(dictDataRaw.entities || {}).length === 0 && Boolean(taxonomyData);
        const dictData = Object.keys(dictDataRaw.entities || {}).length > 0
          ? dictDataRaw
          : (taxonomyData ? buildFallbackDictionaryFromTaxonomy(taxonomyData, selectedOntologyApi) : dictDataRaw);
        const entities = dictData.entities || {};
        const mapPayload = (mapRes.status === 'fulfilled' ? mapRes.value.data : null) || {};
        const mappings = mapPayload.mappings || {};
        const mappingEdges = Array.isArray(mapPayload.mapping_edges) ? mapPayload.mapping_edges : null;

        const synthesizedDictionaryNodes = [
          ...Object.keys(entities).map((entityKey) => ({
            term_id: `${selectedOntologyApi}:${entityKey}`,
            label: entityKey,
            ontology_prefix: selectedOntologyApi,
            source: 'dictionary-class',
            definition: entities[entityKey]?.definition || '',
          })),
          ...Object.keys(dictData.properties || {}).map((propertyKey) => ({
            term_id: `${selectedOntologyApi}:${propertyKey}`,
            label: propertyKey,
            ontology_prefix: selectedOntologyApi,
            source: 'dictionary-datatype-property',
            definition: dictData.properties[propertyKey]?.definition || '',
          })),
          ...Object.keys(dictData.relationships || {}).map((relationshipKey) => ({
            term_id: `${selectedOntologyApi}:${relationshipKey}`,
            label: relationshipKey,
            ontology_prefix: selectedOntologyApi,
            source: 'dictionary-object-property',
            definition: dictData.relationships[relationshipKey]?.definition || '',
          })),
        ];

        const nodes = taxonomyData?.nodes?.length
          ? taxonomyData.nodes
          : synthesizedDictionaryNodes;

        const edges = mappingEdges && mappingEdges.length > 0
          ? mappingEdges.map((edge) => ({
              source_term: edge.source_term || `${selectedMappingType}:${edge.source_label || ''}`,
              source_label: edge.source_label || edge.source_term || '',
              target_term: edge.target_term || `${selectedOntologyApi}:${edge.target_label || ''}`,
              target_label: edge.target_label || edge.target_term || '',
              mapping_type: edge.mapping_type || 'mapsTo',
            }))
          : Object.entries(mappings).map(([sourceKey, targetType]) => {
              const parsed = parseLegacyMappingKey(sourceKey);
              const resolvedTarget = targetType || parsed.targetFromKey || '';
              return {
                source_term: `${selectedMappingType}:${parsed.source}`,
                source_label: parsed.source,
                target_term: `${selectedOntologyApi}:${resolvedTarget}`,
                target_label: resolvedTarget,
                mapping_type: parsed.mappingType,
              };
            });

        const rels = dictData.relationships || {};
        const vocabFromDict = Object.values(rels).flatMap((rel) =>
          (rel.connections || []).map((conn) => ({
            source_term: `${selectedOntologyApi}:${conn.from}`,
            source_label: conn.from,
            target_term: `${selectedOntologyApi}:${conn.to}`,
            target_label: conn.to,
            mapping_type: rel.type || 'relatedTo',
          }))
        );

        if (cancelled) return;
        setOntologyDictionary(dictData);
        setDictionarySourceMode(usingFallbackDictionary ? 'taxonomy-fallback' : 'primary');
        setData({ nodes, edges });
        setMappingEdges(edges);
        setVocabEdges(vocabFromDict);
        setTaxonomy(taxonomyData);
        setReasoning(reasoningData);
        setStats({
          total_terms: taxonomyData
            ? taxonomyData?.summary?.terms ?? nodes.length
            : nodes.length,
          total_vocabulary_mappings: vocabFromDict.length,
          owlready_classes: reasoningData?.summary?.classes ?? taxonomyData?.reasoning_summary?.classes ?? 0,
          owlready_object_properties: reasoningData?.summary?.object_properties ?? taxonomyData?.reasoning_summary?.object_properties ?? 0,
          owlready_datatype_properties: reasoningData?.summary?.datatype_properties ?? taxonomyData?.reasoning_summary?.datatype_properties ?? 0,
          owlready_individuals: reasoningData?.summary?.individuals ?? taxonomyData?.reasoning_summary?.individuals ?? 0,
        });
      } catch (e) {
        if (cancelled) return;
        console.error('Error loading ontology data:', e);
        setError(e.response?.data?.detail || e.message || 'Failed to load ontology data.');
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadMappingData();
    return () => {
      cancelled = true;
    };
  }, [selectedMapping, selectedMappingType, selectedOntologyApi]);

  useEffect(() => {
    let cancelled = false;
    const loadSingleDictionary = async () => {
      if (!selectedOntologyApi) {
        setTargetOntologyDictionary({ entities: {}, relationships: {}, properties: {} });
        setTargetDictionarySourceMode('primary');
        return;
      }
      try {
        const res = await API_METHODS.ontology.getDataDictionary(selectedOntologyApi);
        const dictData = res?.data?.data || {};
        if (Object.keys(dictData.entities || {}).length > 0) {
          if (!cancelled) {
            setTargetOntologyDictionary(dictData);
            setTargetDictionarySourceMode('primary');
          }
          return;
        }
        throw new Error('Empty data dictionary');
      } catch {
        try {
          const taxonomyRes = await API_METHODS.ontology.getTaxonomy(selectedOntologyApi);
          if (!cancelled) {
            const dict = buildFallbackDictionaryFromTaxonomy(taxonomyRes?.data, selectedOntologyApi);
            setTargetOntologyDictionary(dict);
            setTargetDictionarySourceMode('taxonomy-fallback');
          }
          return;
        } catch {
          if (!cancelled) {
            const emptyDict = { entities: {}, relationships: {}, properties: {}, _error: true };
            setTargetOntologyDictionary(emptyDict);
            setTargetDictionarySourceMode('error');
          }
        }
      }
    };

    loadSingleDictionary();
    return () => {
      cancelled = true;
    };
  }, [selectedOntologyApi]);

  useEffect(() => {
    if (sourceEntityOptions.length > 0 && (!bridgeSourceTerm || !sourceEntityOptions.some((option) => option.value === bridgeSourceTerm))) {
      setBridgeSourceTerm(sourceEntityOptions[0].value);
    }
    if (targetEntityOptions.length > 0 && (!bridgeTargetTerm || !targetEntityOptions.some((option) => option.value === bridgeTargetTerm))) {
      setBridgeTargetTerm(targetEntityOptions[0].value);
    }
  }, [sourceEntityOptions, targetEntityOptions, bridgeSourceTerm, bridgeTargetTerm]);

  useEffect(() => {
    if (!selectedMapping) {
      setMergeSourceOntologyId('');
      return;
    }
    if (mergeSourceOntologyId && mergeSourceOntologyId === selectedMapping) {
      setMergeSourceOntologyId('');
      return;
    }
    if (!mergeSourceOntologyId && mergeSourceOptions.length > 0) {
      setMergeSourceOntologyId(mergeSourceOptions[0].value);
    }
  }, [mergeSourceOntologyId, mergeSourceOptions, selectedMapping]);

  const handlePreviewMappings = async () => {
    if (!selectedImportTaskId) {
      setMapMessage({ kind: 'error', text: 'Select an imported instance before previewing mappings.' });
      return;
    }

    setMapBusy(true);
    setMapMessage(null);
    try {
      const taskRes = await API_METHODS.import.getStatus(selectedImportTaskId);
      const taskData = taskRes.data || {};
      const manifest = taskData.artifact_manifest || taskData.artifactManifest || null;
      if (!manifest) {
        throw new Error('Selected instance does not have retained artifacts yet. Import the file first.');
      }

      const previewRes = await API_METHODS.workflow.execute('instance.link', {
        ontology_id: selectedOntologyApi,
        import_artifact_manifest: manifest,
        apply_links: false,
      });
      const previewData = previewRes.data || {};
      const previewCandidates = Array.isArray(previewData?.result?.candidates) ? previewData.result.candidates : [];
      setBridgeCandidates(previewCandidates);
      setUnifyResult(null);
      const summary = previewData?.result?.summary || {};
      setMapMessage({
        kind: 'success',
        text: `Preview ready: ${summary.candidate_count ?? previewCandidates.length} candidates, ${summary.high_confidence_candidates ?? 0} high-confidence.`,
      });
    } catch (e) {
      setMapMessage({ kind: 'error', text: e.response?.data?.detail || e.message || 'Preview failed.' });
    } finally {
      setMapBusy(false);
    }
  };

  const handleUnifyInstanceWithOntology = async () => {
    if (!selectedImportTaskId) {
      setUnifyResult({ kind: 'error', text: 'Select an imported instance to link.' });
      return;
    }
    if (!selectedOntologyApi) {
      setUnifyResult({ kind: 'error', text: 'Select an ontology to link with the instance.' });
      return;
    }

    setUnifyBusy(true);
    setUnifyResult(null);
    try {
      const taskRes = await API_METHODS.import.getStatus(selectedImportTaskId);
      const taskData = taskRes.data || {};
      const manifest = taskData.artifact_manifest || taskData.artifactManifest || null;
      if (!manifest) {
        throw new Error('Selected instance does not have retained artifacts yet. Import the file first.');
      }

      const res = await API_METHODS.workflow.execute('instance.link', {
        ontology_id: selectedOntologyApi,
        import_artifact_manifest: manifest,
        apply_links: true,
      });
      const d = res.data || {};
      const candidates = Array.isArray(d.result?.candidates) ? d.result.candidates : [];
      const approvedCandidates = candidates.filter((candidate) => candidate?.selected_for_apply);
      const approvedRows = approvedCandidates.map((candidate) => ({
        source_instance_id: selectedImportTaskId || candidate.source_instance_id || 'instance',
        source_instance_label: taskData?.filename || candidate.source_instance_label || 'Imported instance',
        source_term: candidate.import_row_key || candidate.source_term || candidate.source_label || selectedImportTaskId || 'instance',
        source_label: candidate.source_label || candidate.import_row_key || candidate.source_term || taskData?.filename || 'Imported entity',
        source_type: candidate.source_type || 'Entity',
        target_term: candidate.ontology_class_element_id || candidate.ontology_term || selectedOntologyApi,
        target_label: candidate.ontology_term || selectedOntologyOption?.label || candidate.ontology_class_element_id || selectedOntologyApi,
        target_ontology_type: candidate.target_ontology_type || 'Class',
        mapping_type: 'autoMap',
        confidence: candidate.confidence,
        evidence: candidate.evidence || [],
        signal_type: candidate.signal_type || 'metadata',
      }));

      setBridgeCandidates(candidates);
      if (approvedRows.length > 0) {
        setMappingEdges((prev) => {
          const next = Array.isArray(prev) ? [...prev] : [];
          approvedRows.forEach((row) => {
            const exists = next.some((edge) =>
              edge?.source_term === row.source_term &&
              String(edge?.mapping_type || '').toLowerCase() === String(row.mapping_type || '').toLowerCase() &&
              edge?.target_term === row.target_term
            );
            if (!exists) next.push(row);
          });
          return next;
        });
      }
      setUnifyResult({
        kind: 'success',
        text: d.result?.summary ? 'Instance linked to ontology.' : d.message || 'Instance linked to ontology.',
        nodes: d.result?.summary?.applied_links,
        summary: d.result?.summary || null,
        candidates,
        manifest: manifest,
      });
    } catch (e) {
      const detail = e?.response?.data?.detail || e?.message || 'Linking failed.';
      setBridgeCandidates([]);
      setUnifyResult({ kind: 'error', text: detail });
    } finally {
      setUnifyBusy(false);
    }
  };

  const handlePreviewOntologyMerge = async () => {
    if (!mergeSourceOntologyId || !selectedMapping) {
      setMergeResult({ kind: 'error', text: 'Select both source and active target ontology before reviewing the merge.' });
      return;
    }
    if (mergeSourceOntologyId === selectedMapping) {
      setMergeResult({ kind: 'error', text: 'Choose two different ontologies for merge.' });
      return;
    }
    setMergeBusy(true);
    setMergeResult(null);
    try {
      const res = await API_METHODS.workflow.execute('ontology.merge', {
        source_ontology_id: mergeSourceOntologyId,
        target_ontology_id: selectedMapping,
      });
      const payload = res.data || {};
      setMergeResult({
        kind: 'success',
        text: 'Merge plan ready. Review overlaps, additions, conflicts, and subclass gaps before commit.',
        task_id: payload.task_id,
        report: payload.result || null,
        artifact_manifest: payload.artifact_manifest || null,
      });
    } catch (e) {
      setMergeResult({ kind: 'error', text: e?.response?.data?.detail || e?.message || 'Merge plan preview failed.' });
    } finally {
      setMergeBusy(false);
    }
  };

  const handleCommitOntologyMerge = async () => {
    if (!mergeSourceOntologyId || !selectedMapping) {
      setMergeResult({ kind: 'error', text: 'Select both source and active target ontology before merging.' });
      return;
    }
    if (mergeSourceOntologyId === selectedMapping) {
      setMergeResult({ kind: 'error', text: 'Choose two different ontologies for merge.' });
      return;
    }
    setMergeBusy(true);
    setMergeResult(null);
    try {
      const res = await API_METHODS.ontology.merge(mergeSourceOntologyId, selectedMapping, { dry_run: false });
      setMergeResult({
        kind: 'success',
        text: res?.data?.message || 'Ontology merge committed to Neo4j.',
        report: res?.data || null,
        artifact_manifest: null,
      });
    } catch (e) {
      setMergeResult({ kind: 'error', text: e?.response?.data?.detail || e?.message || 'Ontology merge failed.' });
    } finally {
      setMergeBusy(false);
    }
  };

  const handleAddBridgeCandidate = (candidate) => {
    if (!candidate) return;
    const newRow = {
      source_instance_id: selectedImportTaskId || candidate.source_instance_id || 'instance',
      source_instance_label: selectedImportTask?.filename || candidate.source_instance_label || 'Imported instance',
      source_term: candidate.import_row_key || candidate.source_term || candidate.source_label || selectedImportTaskId || 'instance',
      source_label: candidate.source_label || candidate.import_row_key || candidate.source_term || selectedImportTask?.filename || 'Imported entity',
      source_type: candidate.source_type || inferBridgeSourceKind({ name: candidate.source_label || candidate.source_term || '' }),
      target_term: candidate.ontology_class_element_id || candidate.ontology_term || selectedOntologyApi,
      target_label: candidate.ontology_term || selectedOntologyOption?.label || candidate.ontology_class_element_id || selectedOntologyApi,
      target_ontology_type: candidate.target_ontology_type || 'Class',
      mapping_type: candidate.selected_for_apply ? 'autoMap' : (candidate.validation_status || 'suggested'),
      confidence: candidate.confidence,
      evidence: candidate.evidence || [],
      signal_type: candidate.signal_type || 'metadata',
      ambiguous: candidate.ambiguous,
      selected_for_apply: true,
      validation_status: candidate.selected_for_apply ? 'approved' : 'suggested',
      approvedByUser: !!candidate.selected_for_apply,
      userComment: candidate.user_comment || '',
    };
    setMappingEdges((prev) => {
      const next = Array.isArray(prev) ? [...prev] : [];
      const exists = next.some((edge) =>
        edge?.source_term === newRow.source_term &&
        String(edge?.mapping_type || '').toLowerCase() === String(newRow.mapping_type || '').toLowerCase() &&
        edge?.target_term === newRow.target_term
      );
      if (!exists) next.push(newRow);
      return next;
    });
    setData((prev) => {
      const prevEdges = Array.isArray(prev?.edges) ? prev.edges : [];
      const exists = prevEdges.some((edge) =>
        edge?.source_term === newRow.source_term &&
        String(edge?.mapping_type || '').toLowerCase() === String(newRow.mapping_type || '').toLowerCase() &&
        edge?.target_term === newRow.target_term
      );
      return {
        ...(prev || { nodes: [] }),
        edges: exists ? prevEdges : [...prevEdges, newRow],
      };
    });
    setSelectedMappingEdgeIndex(visibleMappingEdges.findIndex((edge) => edge?.source_term === newRow.source_term && edge?.target_term === newRow.target_term));
    setMapMessage({ kind: 'success', text: 'Semantic mapping candidate added to the mapping table.' });
  };

  const handleAddBridgeMapping = () => {
    if (!selectedImportTaskId) {
      setMapMessage({ kind: 'error', text: 'Select an imported instance before adding a bridge.' });
      return;
    }
    if (!bridgeSourceTerm || !bridgeTargetTerm) {
      setMapMessage({ kind: 'error', text: 'Select both a source term and a target term before saving a bridge.' });
      return;
    }

    const newRow = {
      source_instance_id: selectedImportTaskId,
      source_instance_label: selectedImportTask?.filename || 'Imported instance',
      source_term: bridgeSourceTerm,
      source_label: bridgeSourceTerm,
      source_type: bridgeSourceKind,
      target_term: bridgeTargetTerm,
      target_label: bridgeTargetTerm,
      target_ontology_type: bridgeTargetKind,
      mapping_type: `${bridgeSourceKind.toLowerCase()}-${bridgeTargetKind.toLowerCase()}`,
      confidence: bridgeApproved ? 1 : 0.75,
      evidence: ['user-selected bridge'],
      signal_type: bridgeSourceKind.toLowerCase(),
      ambiguous: !bridgeApproved,
      selected_for_apply: bridgeApproved,
      validation_status: bridgeApproved ? 'approved' : 'needs_review',
      approvedByUser: bridgeApproved,
      userComment: bridgeComment,
    };

    setMappingEdges((prev) => {
      const next = Array.isArray(prev) ? [...prev] : [];
      const exists = next.some((edge) =>
        edge?.source_term === newRow.source_term &&
        String(edge?.mapping_type || '').toLowerCase() === String(newRow.mapping_type || '').toLowerCase() &&
        edge?.target_term === newRow.target_term
      );
      if (!exists) next.push(newRow);
      return next;
    });
    setData((prev) => {
      const prevEdges = Array.isArray(prev?.edges) ? prev.edges : [];
      const exists = prevEdges.some((edge) =>
        edge?.source_term === newRow.source_term &&
        String(edge?.mapping_type || '').toLowerCase() === String(newRow.mapping_type || '').toLowerCase() &&
        edge?.target_term === newRow.target_term
      );
      return {
        ...(prev || { nodes: [] }),
        edges: exists ? prevEdges : [...prevEdges, newRow],
      };
    });
    setSelectedMappingEdgeIndex(visibleMappingEdges.findIndex((edge) => edge?.source_term === newRow.source_term && edge?.target_term === newRow.target_term));
    setMapMessage({ kind: 'success', text: 'Semantic bridge mapping added to the mapping table.' });
  };

  const handleEditMappingEdge = (edge) => {
    if (!edge) return;
    const sourceLabel = edge.source_label || edge.source_term || '';
    const targetLabel = edge.target_label || edge.target_term || '';
    const sourceKind = edge.source_type || 'Entity';
    const targetKind = edge.target_ontology_type || 'Class';
    if (BRIDGE_SOURCE_KINDS.includes(sourceKind)) {
      setBridgeSourceKind(sourceKind);
    }
    if (BRIDGE_TARGET_KINDS.includes(targetKind)) {
      setBridgeTargetKind(targetKind);
    }
    if (sourceLabel) {
      setBridgeSourceTerm(sourceLabel);
    }
    if (targetLabel) {
      setBridgeTargetTerm(targetLabel);
    }
    setSelectedMappingEdgeIndex(Math.max(0, visibleMappingEdges.findIndex((item) => item?.source_term === edge.source_term && item?.target_term === edge.target_term)));
    setBridgeApproved(Boolean(edge.approvedByUser || edge.selected_for_apply));
    setBridgeComment(edge.userComment || '');
    setMapMessage({
      kind: 'warn',
      text: 'Selected mapping for edit. Adjust the bridge fields above, then save it again.',
    });
  };

  const handleRemoveMappingEdge = (edge) => {
    if (!edge) return;
    setMappingEdges((prev) => (Array.isArray(prev) ? prev.filter((item) => !(
      item?.source_term === edge.source_term &&
      String(item?.mapping_type || '').toLowerCase() === String(edge.mapping_type || '').toLowerCase() &&
      item?.target_term === edge.target_term
    )) : []));
    setData((prev) => {
      const prevEdges = Array.isArray(prev?.edges) ? prev.edges : [];
      return {
        ...(prev || { nodes: [] }),
        edges: prevEdges.filter((item) => !(
          item?.source_term === edge.source_term &&
          String(item?.mapping_type || '').toLowerCase() === String(edge.mapping_type || '').toLowerCase() &&
          item?.target_term === edge.target_term
        )),
      };
    });
    setSelectedMappingEdgeIndex(-1);
    setMapMessage({ kind: 'success', text: 'Mapping removed from the table.' });
  };

  const VIEWS = [
    { id: 'dictionary', label: 'Data Dictionary' },
    { id: 'taxonomy', label: 'Taxonomy / OWL' },
    { id: 'vocabulary', label: 'Mapping Vocabulary' },
    { id: 'alignment', label: 'Semantic Bridge' },
  ];

  return (
    <div style={{ background: C.bg, minHeight: '100%', padding: 0, boxSizing: 'border-box' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: '8px', marginBottom: '8px',
        background: C.surface, border: `1px solid ${C.border}`, borderRadius: '6px', padding: '8px 10px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{
            width: 26,
            height: 26,
            borderRadius: 6,
            display: 'grid',
            placeItems: 'center',
            background: C.primaryLight,
            color: C.primary,
            flex: '0 0 auto',
          }}>
            <Network size={16} strokeWidth={2.4} />
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: '12px', color: C.textPrimary }}>Ontology junction</div>
            <div style={{ fontSize: '10px', color: C.textSec }}>Active ontology, OWL structure, vocabulary, taxonomy, and semantic bridge review.</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', flexDirection: 'column', alignItems: 'flex-start' }}>
          {mappingOptionsError && (
            <div style={{ color: C.red, fontSize: '12px', padding: '8px 12px', background: '#FFE5E5', border: `1px solid ${C.red}`, borderRadius: '6px' }}>
              ⚠️ {mappingOptionsError}
            </div>
          )}

          <>
            <div style={{ display: 'grid', gap: '4px' }}>
              <label style={{ fontSize: '10px', fontWeight: 700, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Active ontology</label>
              <select
                value={selectedMapping}
                onChange={e => {
                  applyOntologySelection(e.target.value);
                }}
                disabled={mappingOptions.length === 0}
                style={{ minWidth: '320px', padding: '6px 10px', background: C.surface, border: `1px solid ${mappingOptionsError ? C.red : C.borderDark}`, color: C.textPrimary, borderRadius: '5px', fontWeight: 600, fontSize: '12px', cursor: mappingOptions.length === 0 ? 'not-allowed' : 'pointer', opacity: mappingOptions.length === 0 ? 0.6 : 1 }}
              >
                <option value="">{mappingOptions.length === 0 ? '— No ontologies loaded —' : '— Select ontology —'}</option>
                {Array.from(new Map(mappingOptions.map(o => [o.prefix, o])).values()).map((o, idx) => (
                  <option key={o.value || `mapping-${idx}`} value={o.value}>
                    {o.label}{o.usageCount ? ` (used ${o.usageCount}x)` : ''}
                  </option>
                ))}
              </select>
            </div>
            {stats && (
              <div style={{ fontSize: '11px', color: C.textSec, background: C.bg, border: `1px solid ${C.border}`, borderRadius: '20px', padding: '4px 10px' }}>
                {stats.total_terms} terms · {stats.total_vocabulary_mappings} mapping edges
              </div>
            )}
          </>
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: C.textSec }}>
          <div style={{ width: 32, height: 32, border: `3px solid ${C.border}`, borderTop: `3px solid ${C.primary}`, borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 12px' }} />
          Loading ontology data…
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      ) : error ? (
        <div style={{ textAlign: 'center', padding: '60px 20px', color: '#d32f2f' }}>

          <div style={{ fontSize: '15px', fontWeight: 600 }}>Failed to load ontology</div>
          <div style={{ fontSize: '12px', marginTop: '6px' }}>{error}</div>
        </div>
      ) : (
        <>
          {/* Sub-tab selector + search bar */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', background: C.surface, border: `1px solid ${C.border}`, borderRadius: '6px', padding: '2px', gap: '1px' }}>
              {VIEWS.map(v => {
                const active = activeView === v.id;
                return (
                  <button key={v.id} onClick={() => { setActiveView(v.id); }}
                    style={{ padding: '5px 10px', border: 'none', borderRadius: '4px', cursor: 'pointer', background: active ? C.primary : 'transparent', color: active ? '#fff' : C.textSec, fontWeight: active ? 700 : 500, fontSize: '11px', transition: 'all .15s' }}>
                    {v.label}
                  </button>
                );
              })}
            </div>

            {/* Search / filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px', flex: '0 1 260px', minWidth: '180px', maxWidth: '260px', background: C.surface, border: `1px solid ${C.borderDark}`, borderRadius: '5px', padding: '5px 8px' }}>
              <Search
                size={13}
                color={C.textMuted}
                strokeWidth={2.2}
                style={{
                  width: 13,
                  height: 13,
                  minWidth: 13,
                  flex: '0 0 13px',
                  background: 'transparent',
                }}
              />
              <input
                type="text" value={filter}
                placeholder={activeView === 'taxonomy' ? 'Find taxonomy term' : activeView === 'vocabulary' ? 'Filter mappings' : 'Filter terms'}
                onChange={e => setFilter(e.target.value)}
                style={{ border: 'none', outline: 'none', fontSize: '13px', lineHeight: '1.4', flex: 1, background: 'transparent', color: C.textPrimary, minHeight: '20px' }}
              />
              {filter && (
                <button onClick={() => setFilter('')} style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.textMuted, padding: 0, display: 'flex', alignItems: 'center', fontSize: '12px' }}>
                  ✕
                </button>
              )}
            </div>
          </div>

          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
            <div style={{ padding: '6px 10px', borderRadius: '999px', border: `1px solid ${C.border}`, background: C.surface, fontSize: '11px', fontWeight: 700, color: C.textPrimary }}>
              {selectedOntologyOption?.label || 'No active ontology selected'}
            </div>
            <div style={{ padding: '6px 10px', borderRadius: '999px', border: `1px solid ${C.border}`, background: C.bg, fontSize: '11px', fontWeight: 700, color: C.textSec }}>
              Prefix {selectedOntologyOption?.prefix || selectedOntologyApi || 'n/a'}
            </div>
            <div style={{ padding: '6px 10px', borderRadius: '999px', border: `1px solid ${dictionarySourceMode === 'taxonomy-fallback' ? '#F7C948' : C.border}`, background: dictionarySourceMode === 'taxonomy-fallback' ? '#FFF8E1' : C.bg, fontSize: '11px', fontWeight: 700, color: dictionarySourceMode === 'taxonomy-fallback' ? '#8A5A00' : C.textSec }}>
              {dictionarySourceMode === 'taxonomy-fallback' ? 'Taxonomy fallback view' : 'Primary ontology dictionary'}
            </div>
            {selectedOntologyOption?.type && (
              <div style={{ padding: '6px 10px', borderRadius: '999px', border: `1px solid ${C.border}`, background: C.bg, fontSize: '11px', fontWeight: 700, color: C.textSec }}>
                Source format {selectedOntologyOption.type}
              </div>
            )}
          </div>

          {activeView !== 'alignment' && dictionarySourceMode === 'taxonomy-fallback' && (
            <div style={{ marginBottom: '8px', padding: '8px 10px', borderRadius: '6px', border: `1px solid ${C.borderDark}`, background: '#FFF8E1', color: C.textPrimary, fontSize: '11px', lineHeight: 1.45 }}>
              Showing taxonomy-derived fallback terms because the primary ontology dictionary is empty for the active ontology. Use this view for inspection, not as proof of full ontology expressivity.
            </div>
          )}

          {/* Legend for relation types (vocabulary view) */}
          {activeView === 'vocabulary' && (
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '12px', padding: '8px 12px', background: C.surface, borderRadius: '8px', border: `1px solid ${C.border}` }}>
              <span style={{ fontSize: '10px', fontWeight: 700, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em', marginRight: '2px' }}>Mapping types:</span>
              {Object.keys(REL_COLORS).map(type => (
                <span key={type} style={{
                  display: 'inline-block', padding: '1px 6px', borderRadius: '10px', fontSize: '9px',
                  background: REL_COLORS[type].bg, color: REL_COLORS[type].text, border: `1px solid ${REL_COLORS[type].border}`,
                  fontWeight: 600, whiteSpace: 'nowrap',
                }}>{type}</span>
              ))}
            </div>
          )}

          {activeView === 'dictionary' && (
            <DataDictionaryTable nodes={data.nodes} filter={filter} prefixFilter={prefixFilter} onPrefixFilterChange={setPrefixFilter} />
          )}
          {activeView === 'taxonomy' && (
            taxonomy?.view_mode === 'classic' ? (
              <TaxonomyView nodes={data.nodes} edges={vocabEdges} filter={filter} taxonomy={taxonomy} reasoning={reasoning} />
            ) : (
              <ProtegeOntologyBrowser nodes={data.nodes} edges={vocabEdges} filter={filter} taxonomy={taxonomy} reasoning={reasoning} />
            )
          )}
          {activeView === 'vocabulary' && (
            <VocabularyTable edges={vocabEdges} filter={filter} />
          )}
          {activeView === 'alignment' && (
            <ErrorBoundary>
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: '8px', padding: '16px', minHeight: '400px' }}>

              {/* ── Link Instance to Ontology ─────────────────────────────── */}
              <div style={{ marginBottom: '20px', border: `2px solid ${C.primary}`, borderRadius: '8px', padding: '16px', background: C.primaryLight }}>
                <div style={{ fontSize: '14px', fontWeight: 700, color: C.primaryDark, marginBottom: '4px' }}>Instance-to-ontology bridge</div>
                <div style={{ fontSize: '12px', color: C.textSec, marginBottom: '14px', lineHeight: 1.45 }}>
                  Step 1: select one imported instance artifact. Step 2: keep the active ontology selected in the page header. Step 3: review auto-suggested mappings before applying them.
                  This bridge links instance entities, attributes, relationships, and metadata to ontology classes and properties. Ontology-to-ontology merge is handled separately below.
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(140px, 1fr))', gap: '8px', marginBottom: '12px' }}>
                  {[
                    { title: '1. Instance', text: selectedImportTaskInfo?.filename || 'Choose imported instance' },
                    { title: '2. Active ontology', text: selectedOntologyOption?.label || 'Choose active ontology' },
                    { title: '3. Review and apply', text: bridgeCandidates.length > 0 ? `${bridgeCandidates.length} candidate mappings ready` : 'Preview suggestions first' },
                  ].map((item) => (
                    <div key={item.title} style={{ border: `1px solid ${C.border}`, borderRadius: '8px', background: C.surface, padding: '8px 10px' }}>
                      <div style={{ fontSize: '10px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{item.title}</div>
                      <div style={{ fontSize: '12px', color: C.textPrimary, fontWeight: 600, marginTop: '4px' }}>{item.text}</div>
                    </div>
                  ))}
                </div>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  gap: '10px',
                  flexWrap: 'wrap',
                  padding: '8px 10px',
                  borderRadius: '8px',
                  border: `1px solid ${C.border}`,
                  background: C.surface,
                  marginBottom: '12px',
                }}>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
                    <span style={{ fontSize: '11px', fontWeight: 700, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Auto-map</span>
                    <span style={{ fontSize: '11px', fontWeight: 700, color: C.primaryDark, background: C.primaryLight, border: `1px solid ${C.border}`, padding: '2px 8px', borderRadius: 999 }}>
                      {bridgeCandidates.length} candidates
                    </span>
                    <span style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary, background: C.bg, border: `1px solid ${C.border}`, padding: '2px 8px', borderRadius: 999 }}>
                      {visibleMappingEdges.length} mappings
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      onClick={handlePreviewMappings}
                      disabled={mapBusy}
                      style={{
                        padding: '7px 12px',
                        border: 'none',
                        borderRadius: '6px',
                        background: mapBusy ? C.textMuted : C.primary,
                        color: '#fff',
                        fontSize: '12px',
                        fontWeight: 700,
                        cursor: mapBusy ? 'not-allowed' : 'pointer',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {mapBusy ? 'Working…' : 'Preview bridge suggestions'}
                    </button>
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '10px', alignItems: 'end' }}>
                  <div>
                    <label style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary, display: 'block', marginBottom: '5px' }}>Instance</label>
                    <select
                      value={selectedImportTaskId}
                      onChange={e => setSelectedImportTaskId(e.target.value)}
                      style={{ width: '100%', padding: '8px 10px', fontSize: '13px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option value="">{importTasksLoading ? 'Loading instances...' : 'Select imported instance'}</option>
                      {importTasks.map((task) => (
                        <option key={task.task_id} value={task.task_id}>
                          {task.filename || task.task_id} {task.status ? `[${task.status}]` : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div style={{ border: `1px solid ${selectedOntologyApi ? C.borderDark : C.red}`, borderRadius: '6px', background: C.surface, padding: '10px 12px', minHeight: '42px' }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary, marginBottom: '4px' }}>Active ontology</div>
                    <div style={{ fontSize: '12px', color: selectedOntologyApi ? C.textPrimary : C.red, fontWeight: 600 }}>
                      {selectedOntologyOption?.label || 'Select an ontology in the header above'}
                    </div>
                    <div style={{ fontSize: '10px', color: C.textSec, marginTop: '4px' }}>
                      {selectedOntologyOption?.prefix ? `Prefix ${selectedOntologyOption.prefix}` : 'The semantic bridge uses the shared active ontology selection.'}
                    </div>
                  </div>
                  <button
                    onClick={handleUnifyInstanceWithOntology}
                    disabled={unifyBusy || !selectedImportTaskId || !selectedOntologyApi}
                    style={{
                      padding: '8px 18px',
                      border: 'none',
                      borderRadius: '6px',
                      background: unifyBusy || !selectedImportTaskId || !selectedOntologyApi ? C.textMuted : C.primaryDark,
                      color: '#fff',
                      fontSize: '13px',
                      fontWeight: 700,
                      cursor: unifyBusy || !selectedImportTaskId || !selectedOntologyApi ? 'not-allowed' : 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {unifyBusy ? 'Linking…' : 'Link'}
                  </button>
                </div>
                <div style={{
                  marginTop: '12px',
                  padding: '10px 12px',
                  borderRadius: '8px',
                  border: `1px solid ${C.border}`,
                  background: C.surface,
                  display: 'grid',
                  gridTemplateColumns: 'repeat(2, minmax(0, 1fr))',
                  gap: '10px 16px',
                }}>
                  <div>
                    <div style={{ fontSize: '10px', color: C.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Instance metadata</div>
                    <div style={{ fontSize: '12px', color: C.textPrimary, fontWeight: 700, marginTop: '3px' }}>
                      {selectedImportTaskInfo?.filename || 'No instance selected'}
                    </div>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      Task {selectedImportTaskInfo?.task_id || 'n/a'} · {selectedImportTaskInfo?.file_type || 'unknown'} · {selectedImportTaskInfo?.status || 'unknown'}{selectedImportTaskInfo?.current_stage ? ` · ${selectedImportTaskInfo.current_stage}` : ''}
                    </div>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      Manifest {selectedImportManifest ? 'available' : 'missing'} · source format {selectedMappingType || 'unknown'}
                    </div>
                  </div>
                  <div>
                    <div style={{ fontSize: '10px', color: C.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Ontology target metadata</div>
                    <div style={{ fontSize: '12px', color: C.textPrimary, fontWeight: 700, marginTop: '3px' }}>
                      {selectedOntologyOption?.label || 'No ontology selected'}
                    </div>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      Prefix {selectedOntologyOption?.prefix || selectedOntologyApi || 'n/a'} · id {selectedOntologyOption?.value || 'n/a'}
                    </div>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      {selectedOntologyOption?.source ? `Registered from ${selectedOntologyOption.source}` : 'Active ontology used as the semantic target for bridge validation and export.'}
                    </div>
                    <div style={{ fontSize: '11px', color: C.textSec, marginTop: '2px' }}>
                      {selectedOntologyOption?.type ? `Ontology role: ${selectedOntologyOption.type.toUpperCase()} semantic model` : 'Ontology role: semantic target model'}
                    </div>
                    {targetDictionarySourceMode === 'taxonomy-fallback' && (
                      <div style={{ fontSize: '11px', color: '#8A5A00', marginTop: '6px' }}>
                        Target ontology dictionary is using taxonomy-derived fallback content for this ontology.
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ marginTop: '8px', fontSize: '11px', color: C.textSec }}>
                  {selectedImportTaskId ? `Auto-detected source format: ${selectedMappingType || 'unknown'}.` : 'Select an imported instance to continue.'}
                </div>
                {(importTasksError || unifyResult) && (
                  <div style={{
                    marginTop: '12px',
                    padding: '10px 14px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: 600,
                    background: (unifyResult && unifyResult.kind === 'error') || importTasksError ? '#FFEBEE' : '#E8F5E9',
                    color: (unifyResult && unifyResult.kind === 'error') || importTasksError ? '#B42318' : '#067647',
                    border: `1px solid ${(unifyResult && unifyResult.kind === 'error') || importTasksError ? '#FFCDD2' : '#C8E6C9'}`,
                  }}>
                    {importTasksError || unifyResult?.text}
                    {unifyResult?.nodes !== undefined && ` (${unifyResult.nodes} links applied)`}
                    {selectedBridgeSummary && (
                      <div style={{ marginTop: '8px', fontWeight: 500, fontSize: '11px', lineHeight: 1.5 }}>
                        {[
                          selectedBridgeSummary.high_confidence_candidates !== undefined ? `High confidence: ${selectedBridgeSummary.high_confidence_candidates}` : null,
                          selectedBridgeSummary.ambiguous_candidates !== undefined ? `Ambiguous: ${selectedBridgeSummary.ambiguous_candidates}` : null,
                          selectedBridgeSummary.generic_matches_filtered !== undefined ? `Filtered: ${selectedBridgeSummary.generic_matches_filtered}` : null,
                          selectedBridgeSummary.metadata_signals_used !== undefined ? `Metadata signals: ${selectedBridgeSummary.metadata_signals_used}` : null,
                          selectedBridgeSummary.applied_links !== undefined ? `Applied links: ${selectedBridgeSummary.applied_links}` : null,
                        ].filter(Boolean).join(' · ')}
                      </div>
                    )}
                  </div>
                )}
                {bridgeCandidates.length > 0 && (
                  <div style={{ marginTop: '12px', border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'auto', maxHeight: '220px', background: C.surface }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead>
                        <tr style={{ background: C.bg }}>
                          <th style={TH({ minWidth: '200px' })}>Source Signal</th>
                          <th style={TH({ minWidth: '200px' })}>Ontology Concept</th>
                          <th style={TH({ width: '90px', textAlign: 'center' })}>Confidence</th>
                          <th style={TH({ minWidth: '160px' })}>Evidence</th>
                          <th style={TH({ width: '120px', textAlign: 'center' })}>Status</th>
                          <th style={TH({ width: '140px', textAlign: 'center' })}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {bridgeCandidates.map((candidate, index) => (
                          <tr key={`${candidate.import_row_key || candidate.source_term || index}-${index}`} style={{ background: index % 2 === 0 ? C.surface : C.bg }}>
                            <td style={TD()}>
                              <div style={{ fontWeight: 600, fontSize: '12px' }}>{candidate.source_term || candidate.import_row_key || 'Imported entity'}</div>
                              <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace' }}>{candidate.source_type || candidate.match_source || candidate.signal_type || 'metadata'}</div>
                            </td>
                            <td style={TD()}>
                              <div style={{ fontWeight: 600, fontSize: '12px' }}>{candidate.ontology_term || 'Ontology concept'}</div>
                              <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace' }}>{candidate.target_ontology_type || 'Class'}</div>
                              <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace' }}>{candidate.ontology_class_element_id || 'n/a'}</div>
                            </td>
                            <td style={TD({ textAlign: 'center' })}>
                              {(Number(candidate.confidence || 0) * 100).toFixed(0)}%
                            </td>
                            <td style={TD()}>
                              <div style={{ fontSize: '10px', color: C.textSec, lineHeight: 1.4 }}>
                                {(candidate.evidence || []).length > 0 ? (candidate.evidence || []).join(', ') : 'row metadata'}
                              </div>
                            </td>
                            <td style={TD({ textAlign: 'center' })}>
                              <span style={{
                                display: 'inline-block',
                                padding: '2px 8px',
                                borderRadius: '10px',
                                fontSize: '10px',
                                fontWeight: 600,
                                background: candidate.selected_for_apply ? '#E8F5E9' : candidate.ambiguous ? '#FFF8E1' : '#EEF2FF',
                                color: candidate.selected_for_apply ? '#067647' : candidate.ambiguous ? '#9A6700' : '#3730A3',
                                border: `1px solid ${candidate.selected_for_apply ? '#C8E6C9' : candidate.ambiguous ? '#FFE08A' : '#C7D2FE'}`,
                              }}>
                                {candidate.selected_for_apply ? 'Auto-applied' : candidate.ambiguous ? 'Review' : 'Suggested'}
                              </span>
                            </td>
                            <td style={TD({ textAlign: 'center' })}>
                              <div style={{ display: 'inline-flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'center' }}>
                                <button
                                  type="button"
                                  onClick={() => handleAddBridgeCandidate(candidate)}
                                  style={{
                                    padding: '4px 8px',
                                    borderRadius: '6px',
                                    border: `1px solid ${C.primary}`,
                                    background: C.primaryLight,
                                    color: C.primaryDark,
                                    fontSize: '10px',
                                    fontWeight: 700,
                                    cursor: 'pointer',
                                  }}
                                >
                                  Add
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleEditMappingEdge({
                                    source_term: candidate.import_row_key || candidate.source_term || '',
                                    source_label: candidate.source_label || candidate.source_term || '',
                                    source_type: candidate.source_type || 'Entity',
                                    target_term: candidate.ontology_class_element_id || candidate.ontology_term || '',
                                    target_label: candidate.ontology_term || candidate.ontology_class_element_id || '',
                                    target_ontology_type: candidate.target_ontology_type || 'Class',
                                    mapping_type: candidate.selected_for_apply ? 'autoMap' : (candidate.validation_status || 'suggested'),
                                    approvedByUser: candidate.selected_for_apply,
                                    userComment: candidate.user_comment || '',
                                  })}
                                  style={{
                                    padding: '4px 8px',
                                    borderRadius: '6px',
                                    border: `1px solid ${C.borderDark}`,
                                    background: C.surface,
                                    color: C.textPrimary,
                                    fontSize: '10px',
                                    fontWeight: 700,
                                    cursor: 'pointer',
                                  }}
                                >
                                  Edit
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', padding: '14px', marginBottom: '16px', background: C.bg }}>
                <div style={{ fontSize: '13px', fontWeight: 700, color: C.textPrimary, marginBottom: '4px' }}>Ontology merge</div>
                <div style={{ fontSize: '11px', color: C.textSec, marginBottom: '12px', lineHeight: 1.45 }}>
                  Use the active ontology as the merge target. Select one other ontology as the source, review the merge plan, then export or commit the merge when the overlap report looks right.
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto auto', gap: '10px', alignItems: 'end' }}>
                  <div>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Source ontology</label>
                    <select
                      value={mergeSourceOntologyId}
                      onChange={(e) => setMergeSourceOntologyId(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option value="">Select source ontology</option>
                      {mergeSourceOptions.map((option) => (
                        <option key={option.value} value={option.value}>{option.label}</option>
                      ))}
                    </select>
                  </div>
                  <div style={{ border: `1px solid ${C.border}`, borderRadius: '6px', background: C.surface, padding: '10px 12px', minHeight: '42px' }}>
                    <div style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary, marginBottom: '4px' }}>Target ontology</div>
                    <div style={{ fontSize: '12px', color: C.textPrimary }}>{selectedOntologyOption?.label || 'Select the active ontology in the header above'}</div>
                  </div>
                  <button
                    type="button"
                    onClick={handlePreviewOntologyMerge}
                    disabled={mergeBusy || !mergeSourceOntologyId || !selectedMapping}
                    style={{ padding: '8px 12px', border: 'none', borderRadius: '6px', background: mergeBusy || !mergeSourceOntologyId || !selectedMapping ? C.textMuted : C.primary, color: '#fff', fontSize: '12px', fontWeight: 700, cursor: mergeBusy || !mergeSourceOntologyId || !selectedMapping ? 'not-allowed' : 'pointer' }}
                  >
                    {mergeBusy ? 'Working...' : 'Review merge plan'}
                  </button>
                  <button
                    type="button"
                    onClick={handleCommitOntologyMerge}
                    disabled={mergeBusy || !mergeSourceOntologyId || !selectedMapping}
                    style={{ padding: '8px 12px', border: 'none', borderRadius: '6px', background: mergeBusy || !mergeSourceOntologyId || !selectedMapping ? C.textMuted : C.primaryDark, color: '#fff', fontSize: '12px', fontWeight: 700, cursor: mergeBusy || !mergeSourceOntologyId || !selectedMapping ? 'not-allowed' : 'pointer' }}
                  >
                    Merge into target
                  </button>
                </div>
                {mergeResult && (
                  <div style={{ marginTop: '12px', padding: '10px 12px', borderRadius: '6px', border: `1px solid ${mergeResult.kind === 'error' ? C.red : C.borderDark}`, background: mergeResult.kind === 'error' ? '#FFE5E5' : C.surface }}>
                    <div style={{ fontSize: '12px', fontWeight: 700, color: mergeResult.kind === 'error' ? C.red : C.textPrimary }}>{mergeResult.text}</div>
                    {mergeResult.report?.summary && (
                      <div style={{ fontSize: '11px', color: C.textSec, marginTop: '6px', lineHeight: 1.45 }}>
                        Overlaps {mergeResult.report.summary.overlap_count ?? 0} | Additions {mergeResult.report.summary.addition_count ?? 0} | Conflicts {mergeResult.report.summary.conflict_count ?? mergeResult.report.conflict_count ?? 0} | Subclass gaps {mergeResult.report.summary.subclass_gap_count ?? 0}
                      </div>
                    )}
                    {mergeResult.report?.candidate_nodes !== undefined && (
                      <div style={{ fontSize: '11px', color: C.textSec, marginTop: '6px', lineHeight: 1.45 }}>
                        Candidate nodes {mergeResult.report.candidate_nodes ?? 0} | Updated nodes {mergeResult.report.nodes_updated ?? 0}
                      </div>
                    )}
                    {mergeResult.artifact_manifest?.artifacts?.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '8px' }}>
                        {mergeResult.artifact_manifest.artifacts.slice(0, 6).map((artifact) => (
                          <a
                            key={artifact.path}
                            href={API_METHODS.workflow.artifactUrl(mergeResult.task_id, artifact.path)}
                            target="_blank"
                            rel="noreferrer"
                            style={{ display: 'inline-flex', alignItems: 'center', padding: '5px 8px', borderRadius: '999px', background: C.primaryLight, color: C.primaryDark, fontSize: '10px', fontWeight: 700, textDecoration: 'none' }}
                          >
                            {artifact.path}
                          </a>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* ── Entity Mapper ───────────────────────────────────────────── */}
              <div style={{ fontSize: '13px', fontWeight: 600, color: C.textPrimary, marginBottom: '10px' }}>Manual override</div>
              <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', padding: '12px', marginBottom: '16px', background: C.bg }}>
                <div style={{ fontSize: '11px', color: C.textSec, marginBottom: '10px', lineHeight: 1.45 }}>
                  <span style={{ color: C.textPrimary, fontWeight: 700 }}>Imported instance:</span> {selectedImportTaskInfo?.filename || 'None'}.
                  Use the reviewed suggestions table for the normal flow. Use this panel only when you need to add or correct one bridge mapping manually.
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '10px', alignItems: 'end' }}>
                  <div>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Source signal type</label>
                    <select
                      value={bridgeSourceKind}
                      onChange={(e) => setBridgeSourceKind(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface, marginBottom: '8px' }}
                    >
                      {BRIDGE_SOURCE_KINDS.map((kind) => (
                        <option key={kind} value={kind}>{kind}</option>
                      ))}
                    </select>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Source term</label>
                    <select
                      value={bridgeSourceTerm}
                      onChange={(e) => setBridgeSourceTerm(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option key="select-src" value="">Select source term</option>
                      {sourceEntityOptions.map((src) => (
                        <option key={src.value} value={src.value}>{src.label}{src.subtitle ? ` - ${src.subtitle}` : ''}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Ontology concept type</label>
                    <select
                      value={bridgeTargetKind}
                      onChange={(e) => setBridgeTargetKind(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface, marginBottom: '8px' }}
                    >
                      {BRIDGE_TARGET_KINDS.map((kind) => (
                        <option key={kind} value={kind}>
                          {kind === 'Class' ? 'Ontology class' : kind.replace('Property', ' property')}
                        </option>
                      ))}
                    </select>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Target term</label>
                    <select
                      value={bridgeTargetTerm}
                      onChange={(e) => setBridgeTargetTerm(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option key="select-target" value="">Select target term</option>
                      {targetEntityOptions.map((target) => (
                        <option key={target.value} value={target.value}>{target.label}{target.subtitle ? ` - ${target.subtitle}` : ''}</option>
                      ))}
                    </select>
                  </div>
                  <div style={{ display: 'grid', gap: '8px', minWidth: 180 }}>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block' }}>User note</label>
                    <input
                      value={bridgeComment}
                      onChange={(e) => setBridgeComment(e.target.value)}
                      placeholder="Optional note"
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    />
                    <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '11px', color: C.textSec }}>
                      <input type="checkbox" checked={bridgeApproved} onChange={(e) => setBridgeApproved(e.target.checked)} />
                      Approved
                    </label>
                    <button
                      onClick={handleAddBridgeMapping}
                      disabled={mapBusy}
                      style={{
                        padding: '8px 14px',
                        border: 'none',
                        borderRadius: '6px',
                        background: mapBusy ? C.textMuted : C.primary,
                        color: '#fff',
                        fontSize: '12px',
                        fontWeight: 700,
                        cursor: mapBusy ? 'not-allowed' : 'pointer',
                      }}
                    >
                      Save bridge
                    </button>
                  </div>
                </div>
                {mapMessage && (
                  <div style={{
                    marginTop: '10px',
                    fontSize: '12px',
                    color: mapMessage.kind === 'error' ? '#B42318' : mapMessage.kind === 'warn' ? '#9A6700' : '#067647',
                  }}>
                    {mapMessage.text}
                  </div>
                )}
              </div>

              {/* ── Mapping Table ───────────────────────────────────────────── */}
              <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'auto', maxHeight: '500px' }}>
                {selectedMappingEdge && (
                  <div style={{ padding: '8px 12px', borderBottom: `1px solid ${C.border}`, background: C.primaryLight, fontSize: '11px', color: C.primaryDark }}>
                    Selected mapping: {selectedMappingEdge.source_label || selectedMappingEdge.source_term || 'source'} → {selectedMappingEdge.target_label || selectedMappingEdge.target_term || 'target'}
                  </div>
                )}
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: C.primary }}>
                      <th style={TH({ minWidth: '220px' })}>Source Term</th>
                      <th style={TH({ minWidth: '150px' })}>Mapping Type</th>
                      <th style={TH({ minWidth: '220px' })}>Target Term</th>
                      <th style={TH({ minWidth: '120px' })}>Review</th>
                      <th style={TH({ width: '210px', textAlign: 'center' })}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleMappingEdges.length > 0 ? (
                      visibleMappingEdges.map((edge, i) => (
                        <tr
                          key={`${edge.source_term}-${edge.mapping_type}-${edge.target_term}`}
                          onClick={() => setSelectedMappingEdgeIndex(i)}
                          style={{
                            background: selectedMappingEdgeIndex === i ? C.primaryLight : (i % 2 === 0 ? C.surface : C.bg),
                            cursor: 'pointer',
                          }}
                        >
                          <td style={TD()}>
                            <div style={{ fontWeight: 600, fontSize: '12px' }}>{edge.source_label || edge.source_term || edge.source_instance_label || 'Imported entity'}</div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace', lineHeight: 1.45 }}>
                              {edge.source_instance_label || 'Imported instance'}{edge.source_instance_id ? ` · ${edge.source_instance_id}` : ''}
                            </div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace', lineHeight: 1.45 }}>
                              term: {edge.source_term || 'n/a'}
                            </div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace', lineHeight: 1.45 }}>
                              type: {edge.source_type || 'Entity'}
                            </div>
                          </td>
                          <td style={TD()}>
                            <span style={{
                              display: 'inline-block', padding: '2px 8px', borderRadius: '10px', fontSize: '10px',
                              background: REL_COLORS[edge.mapping_type]?.bg || C.bg,
                              color: REL_COLORS[edge.mapping_type]?.text || C.textPrimary,
                              border: `1px solid ${REL_COLORS[edge.mapping_type]?.border || C.border}`,
                              fontWeight: 600
                            }}>{edge.mapping_type}</span>
                          </td>
                          <td style={TD()}>
                            <div style={{ fontWeight: 600, fontSize: '12px' }}>{edge.target_label || edge.target_term || 'Ontology class'}</div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace', lineHeight: 1.45 }}>
                              {edge.target_term || 'n/a'}
                            </div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace', lineHeight: 1.45 }}>
                              type: {edge.target_ontology_type || 'Class'}
                            </div>
                          </td>
                          <td style={TD()}>
                            <div style={{ display: 'grid', gap: '4px' }}>
                              <span style={{ display: 'inline-flex', width: 'fit-content', padding: '2px 8px', borderRadius: '999px', fontSize: '10px', fontWeight: 700, background: edge.approvedByUser ? '#E8F5E9' : edge.validation_status === 'needs_review' ? '#FFF8E1' : '#EEF2FF', color: edge.approvedByUser ? '#067647' : edge.validation_status === 'needs_review' ? '#9A6700' : '#3730A3', border: `1px solid ${edge.approvedByUser ? '#C8E6C9' : edge.validation_status === 'needs_review' ? '#FFE08A' : '#C7D2FE'}` }}>
                                {edge.approvedByUser ? 'Approved' : edge.validation_status === 'needs_review' ? 'Needs review' : edge.validation_status || 'Suggested'}
                              </span>
                              <div style={{ fontSize: '10px', color: C.textSec }}>
                                confidence {(Number(edge.confidence || 0) * 100).toFixed(0)}%
                              </div>
                              {edge.userComment && (
                                <div style={{ fontSize: '10px', color: C.textPrimary, lineHeight: 1.35 }}>{edge.userComment}</div>
                              )}
                            </div>
                          </td>
                          <td style={TD({ textAlign: 'center' })}>
                            <div style={{ display: 'inline-flex', gap: '6px', flexWrap: 'wrap', justifyContent: 'center' }}>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setMappingEdges((prev) => (Array.isArray(prev) ? prev.map((item) => (
                                    item?.source_term === edge.source_term && item?.target_term === edge.target_term && String(item?.mapping_type || '').toLowerCase() === String(edge.mapping_type || '').toLowerCase()
                                      ? { ...item, approvedByUser: !edge.approvedByUser, selected_for_apply: !edge.approvedByUser, validation_status: !edge.approvedByUser ? 'approved' : 'needs_review' }
                                      : item
                                  )) : prev));
                                }}
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: '6px',
                                  border: `1px solid ${edge.approvedByUser ? '#C8E6C9' : '#FFE08A'}`,
                                  background: edge.approvedByUser ? '#E8F5E9' : '#FFF8E1',
                                  color: edge.approvedByUser ? '#067647' : '#9A6700',
                                  fontSize: '10px',
                                  fontWeight: 700,
                                  cursor: 'pointer',
                                }}
                              >
                                {edge.approvedByUser ? 'Unapprove' : 'Approve'}
                              </button>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleEditMappingEdge(edge);
                                }}
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: '6px',
                                  border: `1px solid ${C.borderDark}`,
                                  background: C.surface,
                                  color: C.textPrimary,
                                  fontSize: '10px',
                                  fontWeight: 700,
                                  cursor: 'pointer',
                                }}
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  handleRemoveMappingEdge(edge);
                                }}
                                style={{
                                  padding: '4px 8px',
                                  borderRadius: '6px',
                                  border: `1px solid ${C.red}`,
                                  background: '#FFF5F5',
                                  color: C.red,
                                  fontSize: '10px',
                                  fontWeight: 700,
                                  cursor: 'pointer',
                                }}
                              >
                                Remove
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={4} style={{ ...TD(), textAlign: 'center', color: C.textMuted, padding: '24px' }}>
                          No semantic mappings yet. Select an imported instance artifact and ontology, then preview suggestions or add a mapping.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
            </ErrorBoundary>
          )}
        </>
      )}
    </div>
  );
}
