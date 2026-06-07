import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Download } from 'lucide-react';
import { API_METHODS } from '../services/apiClient';
import { useOntologies } from '../contexts/OntologyContext';

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

// ── Main component ─────────────────────────────────────────────────────────────
export default function OntologyMapper() {
  const [data, setData] = useState({ nodes: [], edges: [] });
  const [mappingEdges, setMappingEdges] = useState([]);
  const [vocabEdges, setVocabEdges] = useState([]);
  const [sourceOntologyPrefix, setSourceOntologyPrefix] = useState('');
  const [targetOntologyPrefix, setTargetOntologyPrefix] = useState('');
  const [sourceOntologyDictionary, setSourceOntologyDictionary] = useState({ entities: {}, relationships: {}, properties: {} });
  const [targetOntologyDictionary, setTargetOntologyDictionary] = useState({ entities: {}, relationships: {}, properties: {} });
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
  const [sourceEntityType, setSourceEntityType] = useState('');
  const [targetEntityType, setTargetEntityType] = useState('');
  const [mapBusy, setMapBusy] = useState(false);
  const [mapMessage, setMapMessage] = useState(null);
  const [mergeFromId, setMergeFromId] = useState('');
  const [mergeToId, setMergeToId] = useState('');
  const [mergeBusy, setMergeBusy] = useState(false);
  const [mergeResult, setMergeResult] = useState(null);

  const sourceEntityOptions = useMemo(() => {
    const entities = (sourceOntologyDictionary && sourceOntologyDictionary.entities) || {};
    return Object.keys(entities).sort();
  }, [sourceOntologyDictionary]);

  const targetEntityOptions = useMemo(() => {
    const entities = (targetOntologyDictionary && targetOntologyDictionary.entities) || {};
    return Object.keys(entities).sort();
  }, [targetOntologyDictionary]);

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

  // Get ontology options from centralized context (shared across all components)
  const { ontologies: contextOntologies, fetchOntologies } = useOntologies();

  useEffect(() => {
    // Load available mapping options from centralized context
    // Important: do NOT overwrite Alignment source/target selections on unrelated state changes.
    try {
      setMappingOptionsError(null);
      const options = buildOntologyOptions(contextOntologies || []);
      setMappingOptions(options);

      if (options.length === 0) {
        setMappingOptionsError('No ontologies available. Please upload an ontology first.');
        return;
      }

      // Initialize defaults only once (or if current selection no longer exists)
      const hasSelectedMapping = !!selectedMapping && options.some((o) => o.value === selectedMapping);
      const selectedOption = hasSelectedMapping ? options.find((o) => o.value === selectedMapping) : options[0];
      if (!hasSelectedMapping) {
        setSelectedMapping(selectedOption.value);
      }

      if (!selectedOntologyApi) {
        setSelectedOntologyApi(selectedOption.prefix || selectedOption.ontologyKey || selectedOption.value || '');
      }

      if (!selectedMappingType) {
        setSelectedMappingType(selectedOption.type);
      }

      // Alignment prefixes should be user-controlled; only set if empty
      if (!sourceOntologyPrefix) {
        setSourceOntologyPrefix(selectedOption.prefix || '');
      }
      if (!targetOntologyPrefix) {
        setTargetOntologyPrefix(selectedOption.prefix || '');
      }
    } catch (e) {
      const errorMsg = e.message || 'Failed to process ontologies';
      setMappingOptionsError(errorMsg);
      console.warn('Failed to process ontologies:', e);
    }
  }, [contextOntologies, buildOntologyOptions, selectedMapping, selectedMappingType, selectedOntologyApi, sourceOntologyPrefix, targetOntologyPrefix]);

  useEffect(() => {
    if (!selectedMappingType) {
      setSelectedMappingType(SOURCE_FORMATS[0].id);
    }
  }, [selectedMappingType]);

  useEffect(() => {
    if (!selectedOntologyApi || !selectedMappingType) {
      return;
    }
    // Load data dictionary and vocabulary for selected mapping
    const loadMappingData = async () => {
      setLoading(true);
      setError(null);
      try {
        // Use selectedOntologyApi (the currently selected uploaded ontology prefix).
        // The backend now supports any prefix via generic /{prefix}/data-dictionary routes.
        const [dictRes, mapRes] = await Promise.allSettled([
          API_METHODS.ontology.getDataDictionary(selectedOntologyApi),
          API_METHODS.ontology.getMappings(targetOntologyPrefix || selectedOntologyApi, selectedMappingType),
        ]);

        const dictData = (dictRes.status === 'fulfilled' ? dictRes.value.data.data : null) || {};
        const entities = dictData.entities || {};
        const mapPayload = (mapRes.status === 'fulfilled' ? mapRes.value.data : null) || {};
        const mappings = mapPayload.mappings || {};
        const mappingEdges = Array.isArray(mapPayload.mapping_edges) ? mapPayload.mapping_edges : null;

        const nodes = Object.keys(entities).map((entityKey) => ({
          term_id: `${selectedOntologyApi}:${entityKey}`,
          label: entityKey,
          ontology_prefix: selectedOntologyApi,
        }));

        const edges = mappingEdges && mappingEdges.length > 0
          ? mappingEdges.map((edge) => ({
              source_term: edge.source_term || `${selectedMappingType}:${edge.source_label || ''}`,
              source_label: edge.source_label || edge.source_term || '',
              target_term: edge.target_term || `${targetOntologyPrefix || selectedOntologyApi}:${edge.target_label || ''}`,
              target_label: edge.target_label || edge.target_term || '',
              mapping_type: edge.mapping_type || 'mapsTo',
            }))
          : Object.entries(mappings).map(([sourceKey, targetType]) => {
              const parsed = parseLegacyMappingKey(sourceKey);
              const resolvedTarget = targetType || parsed.targetFromKey || '';
              return {
                source_term: `${selectedMappingType}:${parsed.source}`,
                source_label: parsed.source,
                target_term: `${targetOntologyPrefix || selectedOntologyApi}:${resolvedTarget}`,
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

        setOntologyDictionary(dictData);
        setData({ nodes, edges });
        setMappingEdges(edges);
        setVocabEdges(vocabFromDict);
        setStats({
          total_terms: nodes.length,
          total_vocabulary_mappings: vocabFromDict.length,
        });
      } catch (e) {
        console.error('Error loading ontology data:', e);
        setError(e.response?.data?.detail || e.message || 'Failed to load ontology data.');
      } finally {
        setLoading(false);
      }
    };

    loadMappingData();
  }, [selectedMappingType, selectedOntologyApi, targetOntologyPrefix]);

  useEffect(() => {
    const loadSide = async (prefix, setter) => {
      if (!prefix) {
        setter({ entities: {}, relationships: {}, properties: {} });
        return;
      }
      try {
        const res = await API_METHODS.ontology.getDataDictionary(prefix);
        const dictData = res?.data?.data || {};
        setter(dictData);
      } catch {
        setter({ entities: {}, relationships: {}, properties: {}, _error: true });
      }
    };

    loadSide(sourceOntologyPrefix, setSourceOntologyDictionary);
    loadSide(targetOntologyPrefix, setTargetOntologyDictionary);
  }, [sourceOntologyPrefix, targetOntologyPrefix]);

  useEffect(() => {
    const sources = sourceEntityOptions;
    const targets = targetEntityOptions;

    if (sources.length > 0 && (!sourceEntityType || !sources.includes(sourceEntityType))) {
      setSourceEntityType(sources[0]);
    }
    if (targets.length > 0 && (!targetEntityType || !targets.includes(targetEntityType))) {
      setTargetEntityType(targets[0]);
    }
  }, [sourceEntityOptions, targetEntityOptions, sourceEntityType, targetEntityType]);

  const handleMapEntity = async () => {
    if (!sourceEntityType || !targetEntityType) {
      setMapMessage({ kind: 'error', text: 'Select both source and target entities before mapping.' });
      return;
    }

    setMapBusy(true);
    setMapMessage(null);
    try {
      // Step 5: perform alignment mapping via /api/v1/ontology/{prefix}/map-entity
      const json = await API_METHODS.ontology.mapEntity(targetOntologyPrefix || selectedOntologyApi, {
        entity: {
          id: `ui-map-${Date.now()}`,
          name: sourceEntityType,
          type: sourceEntityType,
          properties: {
            selected_target: targetEntityType,
            mapped_from_ui: true,
            source_ontology: sourceOntologyPrefix,
            target_ontology: targetOntologyPrefix,
          },
        },
        source_format: selectedMappingType,
      });

      const mapRes = json.data || {};
      const mappedType = mapRes?.mapped_entity?.type || '(unknown)';
      const match = mappedType === targetEntityType;

      setMapMessage({
        kind: match ? 'success' : 'warn',
        text: match
          ? `Mapped successfully: ${sourceEntityType} -> ${mappedType}`
          : `Mapped by API to ${mappedType} (selected target was ${targetEntityType})`,
      });
    } catch (e) {
      setMapMessage({ kind: 'error', text: e.response?.data?.detail || e.message || 'Failed to map entity.' });
    } finally {
      setMapBusy(false);
    }
  };

  const handleMerge = async () => {
    if (!mergeFromId || !mergeToId) {
      setMergeResult({ kind: 'error', text: 'Select both a source (FROM) and a destination (INTO) ontology.' });
      return;
    }
    if (mergeFromId === mergeToId) {
      setMergeResult({ kind: 'error', text: 'FROM and INTO ontologies must be different.' });
      return;
    }
    setMergeBusy(true);
    setMergeResult(null);
    try {
      const res = await API_METHODS.ontology.merge(mergeFromId, mergeToId);
      const d = res.data || {};
      setMergeResult({ kind: 'success', text: d.message || 'Merge complete.', nodes: d.nodes_updated });
      // Reload ontology options from context after merge
      const refreshedOntologies = await fetchOntologies();
      const opts = buildOntologyOptions(refreshedOntologies || []);
      setMappingOptions(opts);
      if (opts.length > 0) {
        const stillSelected = opts.find((o) => o.value === selectedMapping);
        const next = stillSelected || opts[0];
        setSelectedMapping(next.value);
        setSelectedMappingType(next.type);
        setSelectedOntologyApi(next.prefix || next.ontologyKey || next.value || '');
      }
      setMergeFromId('');
      setMergeToId('');
    } catch (e) {
      const detail = e.response?.data?.detail || e.message || 'Merge failed.';
      setMergeResult({ kind: 'error', text: detail });
    } finally {
      setMergeBusy(false);
    }
  };

  const VIEWS = [
    { id: 'dictionary', label: '[DOC] Data Dictionary' },
    { id: 'vocabulary', label: '[MAP] Mapping Vocabulary' },
    { id: 'alignment', label: '[SYNC] Ontology Alignment' },
  ];

  return (
    <div style={{ background: C.bg, minHeight: '100%', padding: '20px 24px', boxSizing: 'border-box' }}>
      {/* Header */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: '12px', marginBottom: '20px',
        background: C.surface, border: `1px solid ${C.border}`, borderRadius: '10px', padding: '14px 18px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '22px' }}>🗺️</span>
          <div>
            <div style={{ fontWeight: 800, fontSize: '16px', color: C.textPrimary }}>Semantic Bridge</div>
            <div style={{ fontSize: '12px', color: C.textSec }}>Semantic Mapping — Data Dictionary &amp; Vocabulary</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', flexDirection: 'column', alignItems: 'flex-start' }}>
          {mappingOptionsError && (
            <div style={{ color: C.red, fontSize: '12px', padding: '8px 12px', background: '#FFE5E5', border: `1px solid ${C.red}`, borderRadius: '6px' }}>
              ⚠️ {mappingOptionsError}
            </div>
          )}

          {activeView !== 'alignment' && (
            <>
              <select
                value={selectedMapping}
                onChange={e => {
                  const selected = e.target.value;
                  setSelectedMapping(selected);
                  // [OK] Find the type for this ontology ID and use it for API calls
                  const selectedOption = mappingOptions.find(opt => opt.value === selected);
                  if (selectedOption) {
                    setSelectedOntologyApi(selectedOption.prefix || selectedOption.ontologyKey || selectedOption.value || '');

                    setSourceOntologyPrefix(selectedOption.prefix || '');
                    setTargetOntologyPrefix(selectedOption.prefix || '');
                  }
                  setFilter('');
                }}
                disabled={mappingOptions.length === 0}
                style={{ padding: '7px 12px', background: C.surface, border: `1px solid ${mappingOptionsError ? C.red : C.borderDark}`, color: C.textPrimary, borderRadius: '6px', fontWeight: 600, fontSize: '13px', cursor: mappingOptions.length === 0 ? 'not-allowed' : 'pointer', opacity: mappingOptions.length === 0 ? 0.6 : 1 }}
              >
                <option value="">{mappingOptions.length === 0 ? '— No ontologies loaded —' : '— Select ontology —'}</option>
                {Array.from(new Map(mappingOptions.map(o => [o.prefix, o])).values()).map((o, idx) => (
                  <option key={o.value || `mapping-${idx}`} value={o.value}>
                    {o.label}{o.usageCount ? ` (used ${o.usageCount}x)` : ''}
                  </option>
                ))}
              </select>
              {stats && (
                <div style={{ fontSize: '12px', color: C.textSec, background: C.bg, border: `1px solid ${C.border}`, borderRadius: '20px', padding: '4px 12px' }}>
                  {stats.total_terms} terms · {stats.total_vocabulary_mappings} mapping edges
                </div>
              )}
            </>
          )}
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', background: C.surface, border: `1px solid ${C.border}`, borderRadius: '6px', padding: '2px', gap: '1px' }}>
              {VIEWS.map(v => {
                const active = activeView === v.id;
                return (
                  <button key={v.id} onClick={() => { setActiveView(v.id); setFilter(''); setPrefixFilter(null); }}
                    style={{ padding: '5px 12px', border: 'none', borderRadius: '4px', cursor: 'pointer', background: active ? C.primary : 'transparent', color: active ? '#fff' : C.textSec, fontWeight: active ? 700 : 500, fontSize: '11px', transition: 'all .15s' }}>
                    {v.label}
                  </button>
                );
              })}
            </div>

            {/* Search / filter */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '5px', flex: 1, minWidth: '200px', maxWidth: '380px', background: C.surface, border: `1px solid ${C.borderDark}`, borderRadius: '5px', padding: '6px 8px' }}>
              <span style={{ fontSize: '10px', color: C.textMuted, flexShrink: 0 }}>[FIND]</span>
              <input
                type="text" value={filter}
                placeholder={activeView === 'dictionary' ? 'Filter terms…' : 'Filter mappings…'}
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
          {activeView === 'vocabulary' && (
            <VocabularyTable edges={vocabEdges} filter={filter} />
          )}
          {activeView === 'alignment' && (
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: '8px', padding: '16px', minHeight: '400px' }}>

              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '14px', alignItems: 'end' }}>
                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: C.textSec, display: 'block', marginBottom: '4px' }}>Source Ontology</label>
                  <select
                    value={sourceOntologyPrefix}
                    onChange={(e) => setSourceOntologyPrefix(e.target.value)}
                    style={{ padding: '7px 10px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface, minWidth: '240px' }}
                  >
                    <option value="">— Select source —</option>
                    {mappingOptions.filter(o => o.prefix).map(o => (
                      <option key={`src-${o.value}`} value={o.prefix}>{o.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: C.textSec, display: 'block', marginBottom: '4px' }}>Target Ontology</label>
                  <select
                    value={targetOntologyPrefix}
                    onChange={(e) => setTargetOntologyPrefix(e.target.value)}
                    style={{ padding: '7px 10px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface, minWidth: '240px' }}
                  >
                    <option value="">— Select target —</option>
                    {mappingOptions.filter(o => o.prefix).map(o => (
                      <option key={`tgt-${o.value}`} value={o.prefix}>{o.label}</option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: C.textSec, display: 'block', marginBottom: '4px' }}>Source System</label>
                  <select
                    value={selectedMappingType}
                    onChange={e => setSelectedMappingType(e.target.value)}
                    style={{ padding: '7px 10px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface, minWidth: '160px' }}
                    title="Drives /mappings/{source_format}"
                  >
                    {SOURCE_FORMATS.map((opt) => (
                      <option key={opt.id} value={opt.id}>{opt.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {(sourceOntologyPrefix && sourceOntologyDictionary?._error) || (targetOntologyPrefix && targetOntologyDictionary?._error) ? (
                <div style={{ marginBottom: '14px', padding: '10px 12px', borderRadius: '6px', border: `1px solid ${C.red}`, background: '#FFE5E5', color: C.red, fontSize: '12px', fontWeight: 600 }}>
                  Failed to load one or more data dictionaries for the selected source/target ontologies.
                </div>
              ) : null}

              {/* ── Merge Ontologies ────────────────────────────────────────── */}
              <div style={{ marginBottom: '20px', border: `2px solid ${C.primary}`, borderRadius: '8px', padding: '16px', background: C.primaryLight }}>
                <div style={{ fontSize: '14px', fontWeight: 700, color: C.primaryDark, marginBottom: '4px' }}>[LINK] Merge Ontologies</div>
                <div style={{ fontSize: '12px', color: C.textSec, marginBottom: '14px' }}>
                  All nodes from the <strong>FROM</strong> ontology will be re-stamped with the prefix of the <strong>INTO</strong> ontology and unified in Neo4j.
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr auto', gap: '10px', alignItems: 'end' }}>
                  <div>
                    <label style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary, display: 'block', marginBottom: '5px' }}>FROM (merge source)</label>
                    <select
                      value={mergeFromId}
                      onChange={e => setMergeFromId(e.target.value)}
                      style={{ width: '100%', padding: '8px 10px', fontSize: '13px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option value="">— Select source ontology —</option>
                      {mappingOptions.map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                  <div style={{ fontSize: '20px', color: C.primary, paddingBottom: '2px', alignSelf: 'center' }}>→</div>
                  <div>
                    <label style={{ fontSize: '11px', fontWeight: 700, color: C.textPrimary, display: 'block', marginBottom: '5px' }}>INTO (merge destination)</label>
                    <select
                      value={mergeToId}
                      onChange={e => setMergeToId(e.target.value)}
                      style={{ width: '100%', padding: '8px 10px', fontSize: '13px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option value="">— Select destination ontology —</option>
                      {mappingOptions.filter(o => o.value !== mergeFromId).map(o => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    onClick={handleMerge}
                    disabled={mergeBusy || !mergeFromId || !mergeToId}
                    style={{
                      padding: '8px 18px',
                      border: 'none',
                      borderRadius: '6px',
                      background: mergeBusy || !mergeFromId || !mergeToId ? C.textMuted : C.primaryDark,
                      color: '#fff',
                      fontSize: '13px',
                      fontWeight: 700,
                      cursor: mergeBusy || !mergeFromId || !mergeToId ? 'not-allowed' : 'pointer',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {mergeBusy ? '[WAIT] Merging…' : '[LINK] Merge'}
                  </button>
                </div>
                {mergeResult && (
                  <div style={{
                    marginTop: '12px',
                    padding: '10px 14px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: 600,
                    background: mergeResult.kind === 'error' ? '#FFEBEE' : '#E8F5E9',
                    color: mergeResult.kind === 'error' ? '#B42318' : '#067647',
                    border: `1px solid ${mergeResult.kind === 'error' ? '#FFCDD2' : '#C8E6C9'}`,
                  }}>
                    {mergeResult.text}
                    {mergeResult.nodes !== undefined && ` (${mergeResult.nodes} nodes updated)`}
                  </div>
                )}
              </div>

              {/* ── Entity Mapper ───────────────────────────────────────────── */}
              <div style={{ fontSize: '13px', fontWeight: 600, color: C.textPrimary, marginBottom: '10px' }}>[FIND] Map Individual Entity</div>
              <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', padding: '12px', marginBottom: '16px', background: C.bg }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '10px', alignItems: 'end' }}>
                  <div>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Source Entity</label>
                    <select
                      value={sourceEntityType}
                      onChange={(e) => setSourceEntityType(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option key="select-src" value="">Select source entity</option>
                      {sourceEntityOptions.map((src) => (
                        <option key={src} value={src}>{src}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Target Entity</label>
                    <select
                      value={targetEntityType}
                      onChange={(e) => setTargetEntityType(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option key="select-target" value="">Select target entity</option>
                      {targetEntityOptions.map((target) => (
                        <option key={target} value={target}>{target}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    onClick={handleMapEntity}
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
                    {mapBusy ? 'Mapping...' : 'Map Entity'}
                  </button>
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
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ background: C.primary }}>
                      <th style={TH({ minWidth: '200px' })}>Source Class</th>
                      <th style={TH({ minWidth: '150px' })}>Mapping Type</th>
                      <th style={TH({ minWidth: '200px' })}>Target Class</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(mappingEdges || []).filter(edge => String(edge.mapping_type || '').toLowerCase() !== 'property_of').length > 0 ? (
                      (mappingEdges || []).filter(edge => String(edge.mapping_type || '').toLowerCase() !== 'property_of').map((edge, i) => (
                        <tr key={`${edge.source_term}-${edge.mapping_type}-${edge.target_term}`} style={{ background: i % 2 === 0 ? C.surface : C.bg }}>
                          <td style={TD()}>
                            <div style={{ fontWeight: 600, fontSize: '12px' }}>{edge.source_label || edge.source_term.split(':').pop()}</div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace' }}>{edge.source_term}</div>
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
                            <div style={{ fontWeight: 600, fontSize: '12px' }}>{edge.target_label || edge.target_term.split(':').pop()}</div>
                            <div style={{ fontSize: '10px', color: C.textSec, fontFamily: 'monospace' }}>{edge.target_term}</div>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr><td colSpan={3} style={{ ...TD(), textAlign: 'center', color: C.textMuted, padding: '24px' }}>No entity-to-entity mappings available for this ontology.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

