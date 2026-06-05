import React, { useState, useEffect, useMemo } from 'react';
import { Download } from 'lucide-react';

// ── Design tokens (corporate palette) ─────────────────────────────────────────
const C = {
  primary:      '#004B87',
  primaryDark:  '#003366',
  primaryLight: '#E8F1FC',
  green:        '#28A745',
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

// API Base URL
const API_BASE_URL = 'http://localhost:8000';

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
              <option value="">All Prefixes</option>
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
              const selected = selectedRow === e.source_term + e.target_term;
              return (
                <React.Fragment key={e.source_term + '-' + e.mapping_type + '-' + e.target_term}>
                  <tr
                    onClick={() => setSelectedRow(selected ? null : e.source_term + e.target_term)}
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
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedMapping, setSelectedMapping] = useState('plmxml');
  const [selectedMappingType, setSelectedMappingType] = useState('plmxml');
  const [selectedOntologyApi, setSelectedOntologyApi] = useState('ap239');
  const [activeView, setActiveView] = useState('dictionary');
  const [filter, setFilter] = useState('');
  const [prefixFilter, setPrefixFilter] = useState(null);
  const [mappingOptions, setMappingOptions] = useState([]);
  const [ontologyDictionary, setOntologyDictionary] = useState({ entities: {}, relationships: {}, properties: {} });
  const [ontologyMappings, setOntologyMappings] = useState({});
  const [sourceEntityType, setSourceEntityType] = useState('');
  const [targetEntityType, setTargetEntityType] = useState('');
  const [mapBusy, setMapBusy] = useState(false);
  const [mapMessage, setMapMessage] = useState(null);

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

  useEffect(() => {
    // Load available mapping options from dynamic endpoint
    const loadMappingOptions = async () => {
      try {
        // Try new dynamic endpoint first
        const res = await fetch(`${API_BASE_URL}/ontologies/available`);
        if (res.ok) {
          const json = await res.json();
          // Transform dynamic ontologies to mapping options format
          // IMPORTANT: Store both id (display) and type (for API calls)
          const options = json.ontologies.map(ont => ({
            value: ont.id,
            type: normalizeSourceFormat(ont.type, ont.id),
            ontologyKey: (String(ont.id || '').toLowerCase().includes('ap239') || String(ont.name || '').toLowerCase().includes('ap239')) ? 'ap239' : 'ap239',
            label: ont.name,
            source: ont.source,
            usageCount: ont.usageCount,
          }));
          setMappingOptions(options);
          // Set initial selection to first option's type
          if (options.length > 0) {
            setSelectedMapping(options[0].value);
            setSelectedMappingType(options[0].type);
            setSelectedOntologyApi(options[0].ontologyKey || 'ap239');
          }
          return;
        }
      } catch (e) {
        console.warn('Failed to load dynamic ontologies', e);
      }

      // Fallback to old endpoint if new one fails
      try {
        const res = await fetch(`${API_BASE_URL}/ontology-mapper/options`);
        if (res.ok) {
          const json = await res.json();
          const fallbackOptions = (json.options || []).map(opt => ({
            ...opt,
            type: normalizeSourceFormat(opt.type, opt.value || opt.id),
            ontologyKey: 'ap239',
          }));
          setMappingOptions(fallbackOptions);
          if (fallbackOptions.length > 0) {
            setSelectedMapping(fallbackOptions[0].value || fallbackOptions[0].type || 'plmxml');
            setSelectedMappingType(fallbackOptions[0].type || 'plmxml');
            setSelectedOntologyApi('ap239');
          }
        }
      } catch (e) {
        console.warn('Failed to load mapping options', e);
      }
    };
    loadMappingOptions();
  }, []);

  useEffect(() => {
    // Load data dictionary and vocabulary for selected mapping
    // Step 3: load selected ontology dictionary and mapping rules from /api/v1/ontology/{ontology}/...
    const loadMappingData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [dictRes, mapRes, statsRes] = await Promise.all([
          fetch(`${API_BASE_URL}/api/v1/ontology/${selectedOntologyApi}/data-dictionary`),
          fetch(`${API_BASE_URL}/api/v1/ontology/${selectedOntologyApi}/mappings/${selectedMappingType}`),
          fetch(`${API_BASE_URL}/ontology-mapper/${selectedMappingType}/stats`),
        ]);

        if (dictRes.ok && mapRes.ok) {
          const dictJson = await dictRes.json();
          const mapJson = await mapRes.json();
          const statsJson = statsRes.ok ? await statsRes.json() : null;

          const dictData = dictJson.data || {};
          const entities = dictData.entities || {};
          const mappings = mapJson.mappings || {};

          const nodes = Object.keys(entities).map((entityKey) => ({
            term_id: `${selectedOntologyApi}:${entityKey}`,
            label: entityKey,
            ontology_prefix: selectedOntologyApi,
          }));

          const edges = Object.entries(mappings).map(([sourceType, targetType]) => ({
            source_term: `${selectedMappingType}:${sourceType}`,
            source_label: sourceType,
            target_term: `${selectedOntologyApi}:${targetType}`,
            target_label: targetType,
            mapping_type: 'mapsTo',
          }));

          setOntologyDictionary(dictData);
          setOntologyMappings(mappings);
          setData({ nodes, edges });
          setStats(statsJson || {
            total_terms: nodes.length,
            total_vocabulary_mappings: edges.length,
          });
          return;
        }

        // Fallback to legacy endpoints if the v1 ontology path is unavailable
        const [legacyDictRes, legacyVocabRes, legacyStatsRes] = await Promise.all([
          fetch(`${API_BASE_URL}/ontology-mapper/${selectedMappingType}/data-dictionary`),
          fetch(`${API_BASE_URL}/ontology-mapper/${selectedMappingType}/vocabulary`),
          fetch(`${API_BASE_URL}/ontology-mapper/${selectedMappingType}/stats`),
        ]);

        if (!legacyDictRes.ok || !legacyVocabRes.ok) {
          throw new Error('Failed to load ontology data');
        }

        const legacyDictJson = await legacyDictRes.json();
        const legacyVocabJson = await legacyVocabRes.json();
        const legacyStatsJson = legacyStatsRes.ok ? await legacyStatsRes.json() : null;

        setOntologyDictionary({ entities: {}, relationships: {}, properties: {} });
        setOntologyMappings({});
        setData({
          nodes: legacyDictJson.terms || [],
          edges: legacyVocabJson.mappings || [],
        });
        setStats(legacyStatsJson);
      } catch (e) {
        console.error('Error loading ontology data:', e);
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };

    loadMappingData();
  }, [selectedMappingType, selectedOntologyApi]);

  useEffect(() => {
    const sources = Object.keys(ontologyMappings || {});
    const targets = Object.keys((ontologyDictionary && ontologyDictionary.entities) || {});

    if (sources.length > 0 && !sourceEntityType) {
      setSourceEntityType(sources[0]);
    }
    if (targets.length > 0 && !targetEntityType) {
      setTargetEntityType(targets[0]);
    }
  }, [ontologyMappings, ontologyDictionary, sourceEntityType, targetEntityType]);

  const handleMapEntity = async () => {
    if (!sourceEntityType || !targetEntityType) {
      setMapMessage({ kind: 'error', text: 'Select both source and target entities before mapping.' });
      return;
    }

    setMapBusy(true);
    setMapMessage(null);
    try {
      // Step 5: perform alignment mapping via /api/v1/ontology/{ontology}/map-entity
      const res = await fetch(`${API_BASE_URL}/api/v1/ontology/${selectedOntologyApi}/map-entity`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity: {
            id: `ui-map-${Date.now()}`,
            name: sourceEntityType,
            type: sourceEntityType,
            properties: {
              selected_target: targetEntityType,
              mapped_from_ui: true,
            },
          },
          source_format: selectedMappingType,
        }),
      });

      if (!res.ok) {
        throw new Error(`Mapping API returned ${res.status}`);
      }

      const json = await res.json();
      const mappedType = json?.mapped_entity?.type || '(unknown)';
      const match = mappedType === targetEntityType;

      setMapMessage({
        kind: match ? 'success' : 'warn',
        text: match
          ? `Mapped successfully: ${sourceEntityType} -> ${mappedType}`
          : `Mapped by API to ${mappedType} (selected target was ${targetEntityType})`,
      });
    } catch (e) {
      setMapMessage({ kind: 'error', text: e.message || 'Failed to map entity.' });
    } finally {
      setMapBusy(false);
    }
  };

  const VIEWS = [
    { id: 'dictionary', label: '📖 Data Dictionary' },
    { id: 'vocabulary', label: '🔗 Mapping Vocabulary' },
    { id: 'alignment', label: '🔄 Ontology Alignment' },
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
            <div style={{ fontWeight: 800, fontSize: '16px', color: C.textPrimary }}>Ontology Mapper</div>
            <div style={{ fontSize: '12px', color: C.textSec }}>RML / TTL Mapping — Data Dictionary &amp; Vocabulary</div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
          <select
            value={selectedMapping}
            onChange={e => {
              const selected = e.target.value;
              setSelectedMapping(selected);
              // ✅ Find the type for this ontology ID and use it for API calls
              const selectedOption = mappingOptions.find(opt => opt.value === selected);
              if (selectedOption) {
                setSelectedMappingType(selectedOption.type);
                setSelectedOntologyApi(selectedOption.ontologyKey || 'ap239');
              }
              setFilter('');
            }}
            style={{ padding: '7px 12px', background: C.surface, border: `1px solid ${C.borderDark}`, color: C.textPrimary, borderRadius: '6px', fontWeight: 600, fontSize: '13px', cursor: 'pointer' }}
          >
            {Array.from(new Map(mappingOptions.map(o => [o.value, o])).values()).map(o => (
              <option key={o.value} value={o.value}>
                {o.label}
                {o.usageCount ? ` (used ${o.usageCount}x)` : ''}
                {o.source === 'dynamic' ? ' ✓' : ''}
              </option>
            ))}
          </select>
          {stats && (
            <div style={{ fontSize: '12px', color: C.textSec, background: C.bg, border: `1px solid ${C.border}`, borderRadius: '20px', padding: '4px 12px' }}>
              {stats.total_terms} terms · {stats.total_vocabulary_mappings} mappings
            </div>
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
              <span style={{ fontSize: '10px', color: C.textMuted, flexShrink: 0 }}>🔍</span>
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
            <VocabularyTable edges={data.edges} filter={filter} />
          )}
          {activeView === 'alignment' && (
            <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: '8px', padding: '16px', minHeight: '400px' }}>
              <div style={{ fontSize: '14px', fontWeight: 600, color: C.textPrimary, marginBottom: '12px' }}>Ontology Alignment View</div>
              <p style={{ fontSize: '12px', color: C.textSec, marginBottom: '16px' }}>Step 3 loads dictionary from /api/v1/ontology/{selectedOntologyApi}/data-dictionary, Step 4 lets you choose source/target entities, and Step 5 runs /api/v1/ontology/{selectedOntologyApi}/map-entity.</p>
              
              <div style={{ marginBottom: '16px' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: C.textPrimary, display: 'block', marginBottom: '6px' }}>All Ontologies:</label>
                <select
                  value={selectedMapping}
                  onChange={e => {
                    const selected = e.target.value;
                    setSelectedMapping(selected);
                    const selectedOption = mappingOptions.find(opt => opt.value === selected);
                    if (selectedOption) {
                      setSelectedMappingType(selectedOption.type);
                      setSelectedOntologyApi(selectedOption.ontologyKey || 'ap239');
                    }
                  }}
                  style={{ padding: '8px 12px', fontSize: '13px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', cursor: 'pointer', background: C.surface, minWidth: '300px' }}
                >
                  {mappingOptions.map(o => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                      {o.usageCount ? ` (used ${o.usageCount}x)` : ''}
                      {o.source === 'dynamic' ? ' ✓ in Neo4j' : ''}
                    </option>
                  ))}
                </select>
              </div>

              <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', padding: '12px', marginBottom: '16px', background: C.bg }}>
                <div style={{ fontSize: '12px', fontWeight: 700, color: C.textPrimary, marginBottom: '10px' }}>Map Entity (Step 4 & 5)</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '10px', alignItems: 'end' }}>
                  <div>
                    <label style={{ fontSize: '11px', color: C.textSec, display: 'block', marginBottom: '4px' }}>Source Entity</label>
                    <select
                      value={sourceEntityType}
                      onChange={(e) => setSourceEntityType(e.target.value)}
                      style={{ width: '100%', padding: '7px 8px', fontSize: '12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', background: C.surface }}
                    >
                      <option value="">Select source entity</option>
                      {Object.keys(ontologyMappings || {}).map((src) => (
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
                      <option value="">Select target entity</option>
                      {Object.keys((ontologyDictionary && ontologyDictionary.entities) || {}).map((target) => (
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
                    {data.edges && data.edges.length > 0 ? (
                      data.edges.map((edge, i) => (
                        <tr key={i} style={{ background: i % 2 === 0 ? C.surface : C.bg }}>
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
                      <tr><td colSpan={3} style={{ ...TD(), textAlign: 'center', color: C.textMuted, padding: '24px' }}>No mapping relationships for this ontology.</td></tr>
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

