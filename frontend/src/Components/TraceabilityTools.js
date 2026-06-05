import React, { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import * as d3 from 'd3';
import axios from 'axios';
import config from '../config';
import { GitBranch, ArrowLeftRight, Search, X, ChevronRight, ChevronDown, Info, Loader, Network } from 'lucide-react';

const api = axios.create({ baseURL: config.apiUrl, timeout: 30000 });

// ── Corporate design tokens ────────────────────────────────────────────────────
const C = {
  primary:      '#004B87',
  primaryDark:  '#003366',
  primaryLight: '#E8F1FC',
  orange:       '#FF6900',
  orangeLight:  '#FFF5F0',
  green:        '#28A745',
  greenLight:   '#F0FFF4',
  amber:        '#E6A817',
  amberLight:   '#FFFBEB',
  red:          '#C0392B',
  redLight:     '#FEF2F2',
  textPrimary:  '#1A2B3C',
  textSec:      '#6C757D',
  textMuted:    '#ADB5BD',
  border:       '#E9ECEF',
  borderDark:   '#CED4DA',
  bg:           '#F8F9FA',
  surface:      '#FFFFFF',
};

// ── Mapper column definitions ──────────────────────────────────────────────────
const MAPPER_COLS = {
  ap242:  [{ key:'step_entity',  label:'STEP AP242 Entity' }, { key:'ap242_type',  label:'AP242 Type'     }],
  step:   [{ key:'step_entity',  label:'STEP Entity'       }, { key:'step_id',     label:'STEP ID'        }],
  plmxml: [{ key:'plmxml_file',  label:'PLMXMLFile'        }, { key:'plmxml_node', label:'PLMXML Node'    }, { key:'occurrence_ref', label:'occurrenceRef' }],
};

// ── Helpers ────────────────────────────────────────────────────────────────────
const getLabel = (n) =>
  n?.properties?._name || n?.properties?.name || n?.properties?.item_id ||
  n?.properties?.id    || (n?.labels?.[0] ? `[${n.labels[0]}]` : 'Node');

const getProp = (node, key) => {
  if (!node?.properties) return '—';
  const val = node.properties[key] ?? node.properties[key.replace(/_/g,' ')] ?? null;
  return val != null ? String(val) : '—';
};

// Relationship types that represent BOM/processstructure in Neo4j
const BOM_RELS = new Set([
  'contains','hasChildInstance','referencesProductInstance',
  'DataContainer_Part','Part_Versions','PartVersion_Views',
  'tracesTo','realizes','allocates','linkedTo',
]);

// Build flat ordered tree from traverse response via DFS from root.
// Filters to Individual nodes with meaningful names + BOM-only relationships.
function buildBOMTree(root, nodes, links) {
  if (!root) return [];

  // Include only Individual nodes that have a non-trivial name
  const nodeMap = new Map([[root.elementId, root]]);
  nodes.forEach(n => {
    if (!n.labels?.includes('Individual')) return;
    const disp = n.properties?.name || n.properties?.local_name || '';
    if (!disp || disp.startsWith('http') || /^id\d+$/.test(disp)) return;
    nodeMap.set(n.elementId, n);
  });

  // Only walk BOM-relevant links between known nodes
  const children = new Map();
  links.forEach(l => {
    if (!BOM_RELS.has(l.type)) return;
    const src = l.source || l.start;
    const tgt = l.target || l.end;
    if (src && tgt && nodeMap.has(src) && nodeMap.has(tgt) && src !== tgt) {
      if (!children.has(src)) children.set(src, []);
      children.get(src).push(tgt);
    }
  });

  const result = [];
  const visited = new Set();
  const dfs = (id, level) => {
    if (visited.has(id)) return;
    visited.add(id);
    const node = nodeMap.get(id);
    if (node) result.push({ node, level });
    (children.get(id) || []).forEach(cid => dfs(cid, level + 1));
  };
  dfs(root.elementId, 0);
  nodeMap.forEach((node, id) => {
    if (!visited.has(id)) result.push({ node, level: 1 });
  });
  return result;
}

// Diff two flat BOM lists matched by item key
function diffBOMs(listA, listB) {
  const KEY_PROPS = ['name', 'revision', 'sourceTag', 'rflpLayer', 'type'];
  const keyOf = (r) => {
    const p = r.node.properties;
    if (p?.name) return `${p.name}|${p.revision||''}`;
    return p?.local_name || r.node.elementId;
  };

  const mapA = new Map(listA.map(r => [keyOf(r), r]));
  const mapB = new Map(listB.map(r => [keyOf(r), r]));
  const aOrder = listA.map(r => keyOf(r));
  const bOnly  = listB.map(r => keyOf(r)).filter(k => !mapA.has(k));

  return [...aOrder, ...bOnly].map(k => {
    const a = mapA.get(k), b = mapB.get(k);
    if (a && b) {
      const changedProps = KEY_PROPS.filter(p => String(a.node.properties?.[p]??'') !== String(b.node.properties?.[p]??''));
      return { key: k, a, b, status: changedProps.length > 0 ? 'changed' : 'same', changedProps };
    } else if (a) {
      return { key: k, a, b: null, status: 'removed', changedProps: [] };
    } else {
      return { key: k, a: null, b, status: 'added', changedProps: [] };
    }
  });
}

// ── Shared table primitives ────────────────────────────────────────────────────
const TH = (extra = {}) => ({
  padding: '8px 12px', background: C.primary, color: '#fff',
  fontWeight: 700, fontSize: '11px', textTransform: 'uppercase',
  letterSpacing: '0.04em', textAlign: 'left', whiteSpace: 'nowrap',
  borderRight: `1px solid ${C.primaryDark}`, ...extra,
});
const TD = (extra = {}) => ({
  padding: '7px 12px', borderBottom: `1px solid ${C.border}`,
  fontSize: '13px', color: C.textPrimary, verticalAlign: 'middle', ...extra,
});

// ── Reusable node search panel ─────────────────────────────────────────────────
// Finds which properties matched the search term for display context
const getMatchedProps = (node, term) => {
  if (!node?.properties || !term) return [];
  const kw = term.toLowerCase();
  return Object.entries(node.properties)
    .filter(([, v]) => v != null && String(v).toLowerCase().includes(kw))
    .slice(0, 3)
    .map(([k, v]) => ({ k, v: String(v) }));
};

function NodeSearchPanel({ label, colorAccent, selectedNode, onSelect, onClear }) {
  const [term, setTerm]         = useState('');
  const [lastTerm, setLastTerm] = useState('');
  const [results, setResults]   = useState([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  const search = useCallback(async () => {
    if (!term.trim()) return;
    setLoading(true); setError(''); setResults([]);
    try {
      const res = await api.post('/graphfilter', { search: term.trim() });
      // /graphfilter returns [{ n: { elementId, labels, properties } }, ...]
      const nodes = (res.data?.results || []).map(r => r.n).filter(Boolean);
      setResults(nodes);
      setLastTerm(term.trim());
    } catch (e) {
      setError(e.message || 'Search failed');
    } finally { setLoading(false); }
  }, [term]);

  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      {label && <div style={{ fontWeight: 700, fontSize: '13px', color: colorAccent, marginBottom: '8px' }}>{label}</div>}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
        <input type="text" value={term}
          placeholder="Name, item ID, revision, part number, keyword…"
          onChange={e => setTerm(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()}
          style={{ flex: 1, padding: '8px 12px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', fontSize: '13px', outline: 'none' }}
        />
        <button onClick={search} disabled={loading || !term.trim()}
          style={{ padding: '8px 14px', background: loading ? C.textMuted : colorAccent, color: '#fff', border: 'none', borderRadius: '6px', cursor: loading ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', gap: '5px', fontWeight: 600, fontSize: '13px' }}>
          {loading ? <Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <Search size={13} />}
          {loading ? 'Searching…' : 'Search'}
        </button>
      </div>
      {error && <div style={{ color: C.red, fontSize: '12px', marginBottom: '6px' }}>{error}</div>}
      {selectedNode && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', background: `${colorAccent}15`, border: `1px solid ${colorAccent}40`, borderRadius: '6px', padding: '6px 10px', marginBottom: '8px' }}>
          <span style={{ fontSize: '12px', fontWeight: 700, color: colorAccent, flex: 1 }}>
            Selected: {getLabel(selectedNode)}
            <span style={{ fontWeight: 400, color: C.textSec, marginLeft: '6px' }}>[{(selectedNode.labels||[]).join(', ')}]</span>
          </span>
          <button onClick={onClear} style={{ background: 'none', border: 'none', cursor: 'pointer', color: colorAccent, padding: 0, display: 'flex' }}><X size={13} /></button>
        </div>
      )}
      {results.length > 0 && !selectedNode && (
        <div style={{ border: `1px solid ${C.border}`, borderRadius: '6px', maxHeight: '200px', overflowY: 'auto', background: C.surface }}>
          {results.map((n, i) => {
            const matched = getMatchedProps(n, lastTerm);
            return (
              <button key={n.elementId || i} onClick={() => { onSelect(n); setResults([]); setTerm(''); }}
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', border: 'none', borderBottom: `1px solid ${C.border}`, background: 'transparent', cursor: 'pointer' }}
                onMouseEnter={e => e.currentTarget.style.background = C.primaryLight}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 700, fontSize: '13px', color: colorAccent }}>{getLabel(n)}</span>
                  {n.labels?.length > 0 && <span style={{ fontSize: '10px', color: C.textMuted, background: C.bg, padding: '1px 6px', borderRadius: '8px', border: `1px solid ${C.border}` }}>{n.labels.join(', ')}</span>}
                </div>
                {matched.length > 0 && (
                  <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '3px' }}>
                    {matched.map(({ k, v }) => (
                      <span key={k} style={{ fontSize: '11px', color: C.textSec }}>
                        <span style={{ color: C.textMuted }}>{k}:</span>{' '}
                        <span style={{ fontWeight: 600, color: C.textPrimary }}>{v.length > 40 ? v.slice(0, 40) + '…' : v}</span>
                      </span>
                    ))}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
      {results.length === 0 && !loading && term && !selectedNode && (
        <div style={{ fontSize: '12px', color: C.textMuted }}>No results — press Search or Enter.</div>
      )}
    </div>
  );
}

// ── BOM tree table (used by TraceabilityView) ──────────────────────────────────
function BOMTreeTable({ treeData, mapper, bomType }) {
  const [collapsed, setCollapsed] = useState({});
  const cols = MAPPER_COLS[mapper] || [];
  const isBop = bomType === 'bop';
  const toggle = (key) => setCollapsed(p => ({ ...p, [key]: !p[key] }));

  const visible = useMemo(() => {
    const hiddenIds = new Set();
    treeData.forEach(({ node }, i) => {
      const lvl = treeData[i]?.level ?? 0;
      if (lvl === 0) return;
      for (let j = i - 1; j >= 0; j--) {
        if (treeData[j].level === lvl - 1) {
          const pk = treeData[j].node.elementId + j;
          if (collapsed[pk] || hiddenIds.has(pk)) hiddenIds.add(node.elementId + i);
          break;
        }
      }
    });
    return treeData.map(({ node, level }, i) => ({ node, level, i, hidden: hiddenIds.has(node.elementId + i) }));
  }, [treeData, collapsed]);

  const hasChildren = (i) => treeData[i + 1]?.level > treeData[i].level;

  return (
    <div style={{ overflowX: 'auto', borderRadius: '8px', border: `1px solid ${C.border}`, background: C.surface }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '700px' }}>
        <thead>
          <tr>
            <th style={TH({ minWidth: '260px' })}>Item Name</th>
            <th style={TH({ width: '80px' })}>ID / Key</th>
            <th style={TH({ width: '50px' })}>Level</th>
            <th style={TH({ width: '80px' })}>Labels</th>
            {!isBop && cols.map(c => <th key={c.key} style={TH({ background: C.primaryDark })}>{c.label}</th>)}
            {isBop  && <th style={TH({ background: C.primaryDark })}>Process Type</th>}
          </tr>
        </thead>
        <tbody>
          {visible.map(({ node, level, i, hidden }) => {
            if (hidden) return null;
            const key = node.elementId + i;
            const indent = level * 20;
            const rowBg = level === 0 ? C.primaryLight : i % 2 === 0 ? C.surface : C.bg;
            return (
              <tr key={key} style={{ background: rowBg }}>
                <td style={TD({ paddingLeft: `${12 + indent}px` })}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    {hasChildren(i)
                      ? <button onClick={() => toggle(key)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: C.primary, display: 'flex' }}>
                          {collapsed[key] ? <ChevronRight size={14} strokeWidth={2.5}/> : <ChevronDown size={14} strokeWidth={2.5}/>}
                        </button>
                      : <span style={{ display: 'inline-block', width: 14 }}/>
                    }
                    <span style={{ fontWeight: level===0?800:level===1?600:400, color: level===0?C.primary:C.textPrimary }}>{getLabel(node)}</span>
                  </div>
                </td>
                <td style={TD()}><code style={{ fontSize:'11px', color:C.primary }}>{node.properties?.item_id||node.properties?.id||node.elementId?.slice(-8)||'—'}</code></td>
                <td style={TD({ textAlign:'center', color:C.textSec })}>{level}</td>
                <td style={TD({ fontSize:'11px', color:C.textSec })}>{node.labels?.join(', ')||'—'}</td>
                {!isBop && cols.map(c => (
                  <td key={c.key} style={TD({ fontSize:'12px', color:C.textSec, background:'#FAFBFC' })}>{getProp(node, c.key)}</td>
                ))}
                {isBop && (
                  <td style={TD({ fontSize:'11px' })}>
                    <span style={{ background:C.orangeLight, color:C.orange, padding:'2px 8px', borderRadius:'10px', fontWeight:600 }}>
                      {getProp(node,'process_type')!=='—'?getProp(node,'process_type'):node.labels?.[0]||'—'}
                    </span>
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Tool 1: BOM Traceability ───────────────────────────────────────────────────
function TraceabilityView() {
  const [bomType, setBomType]   = useState('ebom');
  const [mapper, setMapper]     = useState('ap242');
  const [selectedNode, setNode] = useState(null);
  const [treeData, setTree]     = useState([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');

  const loadTree = useCallback(async (node) => {
    setNode(node); setLoading(true); setError(''); setTree([]);
    try {
      const res = await api.get(`/graphtraverse/${encodeURIComponent(node.elementId)}`);
      const rows = res.data?.results || [];
      const nm = new Map(); const links = [];
      rows.forEach(r => {
        if (r.n) nm.set(r.n.elementId, r.n);
        if (r.m) nm.set(r.m.elementId, r.m);
        if (r.r) links.push(r.r);
      });
      setTree(buildBOMTree(nm.get(node.elementId)||node, [...nm.values()], links));
    } catch (e) { setError(e.message||'Failed to load hierarchy'); }
    finally { setLoading(false); }
  }, []);

  const bomColor = { ebom:C.primary, mbom:C.green, bop:C.orange };

  return (
    <div>
      <div style={{ display:'flex', flexWrap:'wrap', gap:'20px', alignItems:'flex-end', marginBottom:'16px', padding:'14px 18px', background:C.surface, borderRadius:'10px', border:`1px solid ${C.border}` }}>
        <div>
          <div style={{ fontSize:'11px', fontWeight:700, color:C.textSec, textTransform:'uppercase', letterSpacing:'0.04em', marginBottom:'6px' }}>BOM Type</div>
          <div style={{ display:'flex', gap:'6px' }}>
            {[['ebom','EBOM'],['mbom','MBOM'],['bop','BOP']].map(([k,l]) => (
              <button key={k} onClick={() => setBomType(k)}
                style={{ background: bomType===k?bomColor[k]:C.surface, color: bomType===k?'#fff':C.textSec, fontWeight: bomType===k?700:500, border:`1px solid ${bomType===k?bomColor[k]:C.border}`, borderRadius:'5px', padding:'6px 16px', cursor:'pointer', fontSize:'13px' }}>
                {l}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div style={{ fontSize:'11px', fontWeight:700, color:C.textSec, textTransform:'uppercase', letterSpacing:'0.04em', marginBottom:'6px' }}>Standard Mapper</div>
          <select value={mapper} onChange={e => setMapper(e.target.value)}
            style={{ padding:'7px 12px', borderRadius:'6px', border:`1px solid ${C.borderDark}`, fontSize:'13px', fontWeight:600, color:C.textPrimary, background:C.surface }}>
            <option value="ap242">STEP AP242</option>
            <option value="step">STEP (ISO 10303)</option>
            <option value="plmxml">PLMXML</option>
          </select>
        </div>
        <div style={{ flex:1, minWidth:'260px' }}>
          <div style={{ fontSize:'11px', fontWeight:700, color:C.textSec, textTransform:'uppercase', letterSpacing:'0.04em', marginBottom:'6px' }}>Search Assembly / Part</div>
          <NodeSearchPanel label="" colorAccent={bomColor[bomType]}
            selectedNode={selectedNode}
            onSelect={loadTree}
            onClear={() => { setNode(null); setTree([]); }} />
        </div>
      </div>

      {loading && <div style={{ display:'flex', alignItems:'center', gap:'10px', padding:'20px', color:C.textSec, fontSize:'13px' }}><Loader size={16} style={{ animation:'spin 1s linear infinite', color:C.primary }}/> Loading BOM hierarchy…</div>}
      {error   && <div style={{ color:C.red, fontSize:'13px', padding:'10px 0' }}>{error}</div>}
      {!loading && !error && treeData.length === 0 && (
        <div style={{ textAlign:'center', padding:'48px 20px', color:C.textMuted }}>
          <GitBranch size={36} style={{ color:C.textMuted, marginBottom:'12px' }}/>
          <div style={{ fontSize:'14px', fontWeight:600 }}>Search for an assembly or part to view its BOM hierarchy</div>
          <div style={{ fontSize:'12px', marginTop:'6px' }}>Results load live from the knowledge graph</div>
        </div>
      )}
      {!loading && treeData.length > 0 && <BOMTreeTable treeData={treeData} mapper={mapper} bomType={bomType}/>}
    </div>
  );
}

// ── Tool 2: BOM Comparison ─────────────────────────────────────────────────────
const STATUS_STYLE = {
  same:    { bg:C.surface,    symbol:'=', color:C.textMuted, title:'Identical — same in both BOMs'     },
  changed: { bg:C.amberLight, symbol:'~', color:C.amber,     title:'Changed — value differs between A and B' },
  removed: { bg:C.redLight,   symbol:'−', color:C.red,       title:'Removed — only exists in BOM A'    },
  added:   { bg:C.greenLight, symbol:'+', color:C.green,     title:'Added — only exists in BOM B'      },
};
const KEY_FIELDS = [
  { key:'name',      label:'Name'     },
  { key:'revision',  label:'Revision' },
  { key:'sourceTag', label:'Type'     },
  { key:'rflpLayer', label:'Layer'    },
  { key:'type',      label:'Subtype'  },
];

function BOMComparison() {
  const [nodeA, setNodeA] = useState(null); const [treeA, setTreeA] = useState([]); const [loadingA, setLoadingA] = useState(false); const [errA, setErrA] = useState('');
  const [nodeB, setNodeB] = useState(null); const [treeB, setTreeB] = useState([]); const [loadingB, setLoadingB] = useState(false); const [errB, setErrB] = useState('');

  const fetchTree = useCallback(async (node, side) => {
    const [setN, setT, setL, setE] = side==='A'
      ? [setNodeA,setTreeA,setLoadingA,setErrA]
      : [setNodeB,setTreeB,setLoadingB,setErrB];
    setN(node); setL(true); setE(''); setT([]);
    try {
      const res = await api.get(`/graphtraverse/${encodeURIComponent(node.elementId)}`);
      const rows = res.data?.results||[]; const nm=new Map(); const links=[];
      rows.forEach(r => { if(r.n)nm.set(r.n.elementId,r.n); if(r.m)nm.set(r.m.elementId,r.m); if(r.r)links.push(r.r); });
      setT(buildBOMTree(nm.get(node.elementId)||node,[...nm.values()],links));
    } catch(e){ setE(e.message||'Failed'); } finally{ setL(false); }
  }, []);

  const diffRows = useMemo(() => (treeA.length>0&&treeB.length>0) ? diffBOMs(treeA,treeB) : [], [treeA,treeB]);
  const counts   = useMemo(() => ({ same:diffRows.filter(r=>r.status==='same').length, changed:diffRows.filter(r=>r.status==='changed').length, removed:diffRows.filter(r=>r.status==='removed').length, added:diffRows.filter(r=>r.status==='added').length }), [diffRows]);

  const cellVal = (row, side, fk) => {
    const r = side==='A'?row.a:row.b;
    if (!r) return <span style={{color:C.textMuted}}>—</span>;
    const val = r.node.properties?.[fk]??'—';
    const changed = row.status==='changed' && row.changedProps.includes(fk);
    return <span style={{fontWeight:changed?700:400, color:changed?C.amber:C.textPrimary}}>{String(val)}</span>;
  };

  return (
    <div>
      {/* Color legend */}
      <div style={{ display:'flex', gap:'8px', flexWrap:'wrap', alignItems:'center', marginBottom:'14px', padding:'10px 14px', background:C.surface, borderRadius:'8px', border:`1px solid ${C.border}` }}>
        <span style={{ fontSize:'11px', fontWeight:700, color:C.textSec, textTransform:'uppercase', letterSpacing:'0.05em', marginRight:'4px' }}>Legend:</span>
        {Object.entries(STATUS_STYLE).map(([k,s]) => (
          <span key={k} style={{ display:'inline-flex', alignItems:'center', gap:'5px', padding:'3px 10px', borderRadius:'12px', background:s.bg, border:`1px solid ${s.color}40`, fontSize:'12px' }}>
            <span style={{ fontWeight:900, color:s.color, fontSize:'14px', lineHeight:1 }}>{s.symbol}</span>
            <span style={{ color:C.textPrimary }}>{s.title}</span>
          </span>
        ))}
      </div>

      {/* Two search panels */}
      <div style={{ display:'flex', gap:'20px', marginBottom:'16px', flexWrap:'wrap' }}>
        <div style={{ flex:1, minWidth:'260px', padding:'14px 18px', background:C.surface, borderRadius:'10px', border:`2px solid ${C.primary}40` }}>
          <NodeSearchPanel label="BOM A — Baseline" colorAccent={C.primary} selectedNode={nodeA}
            onSelect={n=>fetchTree(n,'A')} onClear={()=>{setNodeA(null);setTreeA([]);}} />
          {loadingA && <div style={{fontSize:'12px',color:C.textSec,marginTop:'6px',display:'flex',gap:6}}><Loader size={12} style={{animation:'spin 1s linear infinite'}}/>Loading…</div>}
          {errA     && <div style={{fontSize:'12px',color:C.red,marginTop:'6px'}}>{errA}</div>}
          {treeA.length>0 && <div style={{fontSize:'11px',color:C.primary,marginTop:'6px',fontWeight:600}}>{treeA.length} nodes loaded</div>}
        </div>
        <div style={{ display:'flex', alignItems:'center', fontSize:'20px', color:C.textMuted }}>↔</div>
        <div style={{ flex:1, minWidth:'260px', padding:'14px 18px', background:C.surface, borderRadius:'10px', border:`2px solid ${C.green}40` }}>
          <NodeSearchPanel label="BOM B — Compare" colorAccent={C.green} selectedNode={nodeB}
            onSelect={n=>fetchTree(n,'B')} onClear={()=>{setNodeB(null);setTreeB([]);}} />
          {loadingB && <div style={{fontSize:'12px',color:C.textSec,marginTop:'6px',display:'flex',gap:6}}><Loader size={12} style={{animation:'spin 1s linear infinite'}}/>Loading…</div>}
          {errB     && <div style={{fontSize:'12px',color:C.red,marginTop:'6px'}}>{errB}</div>}
          {treeB.length>0 && <div style={{fontSize:'11px',color:C.green,marginTop:'6px',fontWeight:600}}>{treeB.length} nodes loaded</div>}
        </div>
      </div>

      {diffRows.length===0 && !loadingA && !loadingB && (
        <div style={{ textAlign:'center', padding:'48px 20px', color:C.textMuted }}>
          <ArrowLeftRight size={36} style={{color:C.textMuted,marginBottom:'12px'}}/>
          <div style={{fontSize:'14px',fontWeight:600}}>Search and select two BOMs above to compare them</div>
          <div style={{fontSize:'12px',marginTop:'6px'}}>Differences are highlighted row-by-row using the legend above</div>
        </div>
      )}

      {diffRows.length>0 && (
        <>
          <div style={{ display:'flex', gap:'10px', flexWrap:'wrap', marginBottom:'10px', alignItems:'center' }}>
            {[['same',C.textMuted,'Identical'],['changed',C.amber,'Changed'],['removed',C.red,'Only in A'],['added',C.green,'Only in B']].map(([k,col,lbl])=>(
              <div key={k} style={{display:'inline-flex',alignItems:'center',gap:'6px',padding:'4px 12px',borderRadius:'20px',background:`${col}18`,border:`1px solid ${col}40`,fontSize:'12px',fontWeight:700}}>
                <span style={{color:col}}>{counts[k]}</span><span style={{color:C.textSec}}>{lbl}</span>
              </div>
            ))}
            <span style={{marginLeft:'auto',fontSize:'11px',color:C.textMuted}}>A: {getLabel(nodeA)} ↔ B: {getLabel(nodeB)}</span>
          </div>

          <div style={{ overflowX:'auto', borderRadius:'8px', border:`1px solid ${C.border}`, background:C.surface }}>
            <table style={{ width:'100%', borderCollapse:'collapse', minWidth:'800px' }}>
              <thead>
                <tr>
                  <th style={TH({width:'32px',textAlign:'center',padding:'8px 6px'})}>Δ</th>
                  <th style={TH({background:`${C.primary}CC`})} colSpan={KEY_FIELDS.length}>BOM A — {getLabel(nodeA)}</th>
                  <th style={TH({background:`${C.green}CC`})}  colSpan={KEY_FIELDS.length}>BOM B — {getLabel(nodeB)}</th>
                </tr>
                <tr>
                  <th style={TH({background:'#2d3e50',padding:'6px'})}></th>
                  {KEY_FIELDS.map(f=><th key={'a-'+f.key} style={TH({background:`${C.primary}99`,fontSize:'10px'})}>{f.label}</th>)}
                  {KEY_FIELDS.map(f=><th key={'b-'+f.key} style={TH({background:`${C.green}99`,fontSize:'10px'})}>{f.label}</th>)}
                </tr>
              </thead>
              <tbody>
                {diffRows.map((row,i)=>{
                  const st=STATUS_STYLE[row.status];
                  const rowBg=row.status!=='same'?st.bg:i%2===0?C.surface:C.bg;
                  return (
                    <tr key={row.key+i} style={{background:rowBg}}>
                      <td style={TD({textAlign:'center',fontWeight:800,fontSize:'14px',color:st.color,background:st.bg,padding:'4px'})} title={st.title}>{st.symbol}</td>
                      {KEY_FIELDS.map((f,idx)=><td key={'a-'+f.key} style={TD({borderRight:idx===KEY_FIELDS.length-1?`2px solid ${C.border}`:undefined})}>{cellVal(row,'A',f.key)}</td>)}
                      {KEY_FIELDS.map(f=><td key={'b-'+f.key} style={TD()}>{cellVal(row,'B',f.key)}</td>)}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

// ── Tool 3: Traceability Graph ─────────────────────────────────────────────────
// Layer classification: colours nodes by their engineering domain layer
const LAYER_DEF = {
  ebom:  { label:'EBOM',     color:'#004B87', bg:'#E8F1FC', match: p => p.sourceTag==='ItemRevision' || p.type==='ItemRevision'  },
  mbom:  { label:'MBOM',     color:'#28A745', bg:'#F0FFF4', match: p => (p.name||'').toLowerCase().startsWith('mbom') || (p.name||'').toLowerCase().startsWith('m bom') },
  bop:   { label:'BOP',      color:'#FF6900', bg:'#FFF5F0', match: p => p.sourceTag==='ProcessRevision' || p.type==='ProcessRevision' },
  step:  { label:'STEP CAD', color:'#6F42C1', bg:'#F5F0FF', match: p => p.sourceTag==='ExternalFile' || /\.(stp|step|jt|prt)/i.test(p.name||'') },
  req:   { label:'Requirements', color:'#DC3545', bg:'#FEF2F2', match: p => /requirement|req/i.test(p.sourceTag||p.type||p.name||'') },
  other: { label:'Other',    color:'#6C757D', bg:'#F8F9FA', match: () => true },
};
const getNodeLayer = (node) => {
  const p = node.properties || {};
  for (const [k, def] of Object.entries(LAYER_DEF)) {
    if (k !== 'other' && def.match(p)) return k;
  }
  return 'other';
};

function TraceabilityGraph() {
  const [selectedNode, setNode] = useState(null);
  const [graphData, setGraph]   = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState('');
  const [hiddenLayers, setHiddenLayers] = useState(new Set(['other']));
  const [highlightLayer, setHighlight]  = useState(null);
  const [tooltip, setTooltip]   = useState(null);
  const svgRef = useRef(null);
  const simRef = useRef(null);

  // Load traversal data when a node is selected
  const loadGraph = useCallback(async (node) => {
    setNode(node); setLoading(true); setError(''); setGraph(null);
    try {
      const res = await api.get(`/graphtraverse/${encodeURIComponent(node.elementId)}`);
      const rows = res.data?.results || [];
      const nm = new Map(); const links = [];
      rows.forEach(r => {
        if (r.n) nm.set(r.n.elementId, r.n);
        if (r.m) nm.set(r.m.elementId, r.m);
        if (r.r && r.r.start && r.r.end) links.push(r.r);
      });
      // Filter meaningful Individual nodes
      const nodes = [...nm.values()].filter(n => {
        if (!n.labels?.includes('Individual')) return false;
        const disp = n.properties?.name || n.properties?.local_name || '';
        return disp && !disp.startsWith('http') && !/^id\d+$/.test(disp);
      });
      // Ensure root is always included
      if (!nodes.find(n => n.elementId === node.elementId)) nodes.unshift(node);
      setGraph({ nodes, links });
    } catch(e) { setError(e.message || 'Failed to load graph'); }
    finally { setLoading(false); }
  }, []);

  // D3 force simulation
  useEffect(() => {
    if (!graphData || !svgRef.current) return;
    const { nodes: rawNodes, links: rawLinks } = graphData;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const W = svgRef.current.clientWidth || 900;
    const H = 520;
    const visNodes = rawNodes.filter(n => !hiddenLayers.has(getNodeLayer(n)));
    const nodeIds  = new Set(visNodes.map(n => n.elementId));
    const visLinks = rawLinks.filter(l => nodeIds.has(l.start) && nodeIds.has(l.end));

    const g = svg.append('g');
    svg.call(d3.zoom().scaleExtent([0.2, 3]).on('zoom', e => g.attr('transform', e.transform)));

    // Arrow marker
    svg.append('defs').append('marker')
      .attr('id','arrowhead').attr('viewBox','0 -4 8 8').attr('refX',14).attr('refY',0)
      .attr('markerWidth',6).attr('markerHeight',6).attr('orient','auto')
      .append('path').attr('d','M0,-4L8,0L0,4').attr('fill','#aaa');

    const link = g.append('g').selectAll('line').data(visLinks).join('line')
      .attr('stroke','#CBD5E0').attr('stroke-width',1.2).attr('marker-end','url(#arrowhead)');

    const node = g.append('g').selectAll('g').data(visNodes).join('g')
      .style('cursor','pointer')
      .call(d3.drag()
        .on('start', (ev, d) => { if (!ev.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
        .on('drag',  (ev, d) => { d.fx=ev.x; d.fy=ev.y; })
        .on('end',   (ev, d) => { if (!ev.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }));

    node.append('circle')
      .attr('r', d => d.elementId === rawNodes[0].elementId ? 14 : 9)
      .attr('fill', d => {
        const lk = getNodeLayer(d);
        const hl = highlightLayer;
        if (hl && lk !== hl) return '#E9ECEF';
        return LAYER_DEF[lk].color;
      })
      .attr('stroke', d => d.elementId === rawNodes[0].elementId ? '#fff' : 'none')
      .attr('stroke-width', 3)
      .attr('opacity', 0.9);

    node.append('text')
      .text(d => { const n = getLabel(d); return n.length > 22 ? n.slice(0,20)+'…' : n; })
      .attr('x', 12).attr('y', 4)
      .attr('font-size', '10px').attr('fill', '#374151').attr('pointer-events','none');

    node.on('mouseenter', (ev, d) => {
      const p = d.properties || {};
      setTooltip({ x: ev.clientX+12, y: ev.clientY-10, name: getLabel(d), rev: p.revision, type: p.sourceTag||p.type, layer: getNodeLayer(d) });
    }).on('mouseleave', () => setTooltip(null));

    const nodeEids = new Map(visNodes.map(n => [n.elementId, n]));
    const simLinks = visLinks.map(l => ({ source: nodeEids.get(l.start)||l.start, target: nodeEids.get(l.end)||l.end }));

    const sim = d3.forceSimulation(visNodes)
      .force('link', d3.forceLink(simLinks).id(d => d.elementId).distance(80).strength(0.5))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(W/2, H/2))
      .force('collision', d3.forceCollide(20))
      .on('tick', () => {
        link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y)
            .attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);
        node.attr('transform', d => `translate(${d.x},${d.y})`);
      });
    simRef.current = sim;
    return () => sim.stop();
  }, [graphData, hiddenLayers, highlightLayer]);

  const toggleLayer = (k) => setHiddenLayers(p => {
    const s = new Set(p); s.has(k) ? s.delete(k) : s.add(k); return s;
  });

  return (
    <div>
      <div style={{ padding:'14px 18px', background:C.surface, borderRadius:'10px', border:`1px solid ${C.border}`, marginBottom:'16px' }}>
        <div style={{ fontSize:'11px', fontWeight:700, color:C.textSec, textTransform:'uppercase', letterSpacing:'0.04em', marginBottom:'8px' }}>
          Search Assembly / Part to visualise as graph
        </div>
        <NodeSearchPanel label="" colorAccent={C.primary}
          selectedNode={selectedNode}
          onSelect={loadGraph}
          onClear={() => { setNode(null); setGraph(null); }} />
      </div>

      {/* Layer toggle buttons */}
      <div style={{ display:'flex', gap:'8px', flexWrap:'wrap', alignItems:'center', marginBottom:'12px' }}>
        <span style={{ fontSize:'11px', fontWeight:700, color:C.textSec, textTransform:'uppercase', letterSpacing:'0.04em' }}>Layers:</span>
        {Object.entries(LAYER_DEF).map(([k, def]) => {
          const hidden = hiddenLayers.has(k);
          const highlighted = highlightLayer === k;
          return (
            <span key={k} style={{ display:'inline-flex', gap:'4px' }}>
              <button onClick={() => toggleLayer(k)}
                title={hidden ? `Show ${def.label}` : `Hide ${def.label}`}
                style={{ padding:'4px 12px', borderRadius:'6px 0 0 6px', border:`1px solid ${def.color}`, background: hidden ? '#fff' : def.bg, color: hidden ? '#aaa' : def.color, fontWeight:700, fontSize:'12px', cursor:'pointer', textDecoration: hidden ? 'line-through' : 'none', opacity: hidden ? 0.5 : 1 }}>
                {def.label}
              </button>
              <button onClick={() => setHighlight(p => p===k ? null : k)}
                title={highlighted ? 'Remove highlight' : `Highlight ${def.label}`}
                style={{ padding:'4px 8px', borderRadius:'0 6px 6px 0', border:`1px solid ${def.color}`, borderLeft:'none', background: highlighted ? def.color : '#fff', color: highlighted ? '#fff' : def.color, fontWeight:700, fontSize:'11px', cursor:'pointer' }}>
                ★
              </button>
            </span>
          );
        })}
        {(hiddenLayers.size > 0 || highlightLayer) && (
          <button onClick={() => { setHiddenLayers(new Set(['other'])); setHighlight(null); }}
            style={{ padding:'4px 10px', background:'none', border:`1px solid ${C.border}`, borderRadius:'6px', fontSize:'11px', color:C.textSec, cursor:'pointer' }}>
            Reset
          </button>
        )}
        {graphData && <span style={{ marginLeft:'auto', fontSize:'11px', color:C.textMuted }}>{graphData.nodes.filter(n=>!hiddenLayers.has(getNodeLayer(n))).length} visible nodes</span>}
      </div>

      {loading && <div style={{ display:'flex', alignItems:'center', gap:'10px', padding:'20px', color:C.textSec, fontSize:'13px' }}><Loader size={16} style={{ animation:'spin 1s linear infinite', color:C.primary }}/> Loading graph…</div>}
      {error   && <div style={{ color:C.red, fontSize:'13px', padding:'10px 0' }}>{error}</div>}

      {!loading && !graphData && (
        <div style={{ textAlign:'center', padding:'60px 20px', color:C.textMuted }}>
          <Network size={40} style={{ color:C.textMuted, marginBottom:'12px' }}/>
          <div style={{ fontSize:'14px', fontWeight:600 }}>Search for any node to visualise its traceability graph</div>
          <div style={{ fontSize:'12px', marginTop:'6px' }}>Toggle EBOM / MBOM / BOP / STEP CAD layer buttons to show or hide groups</div>
        </div>
      )}

      {graphData && (
        <div style={{ position:'relative', background:C.surface, border:`1px solid ${C.border}`, borderRadius:'10px', overflow:'hidden' }}>
          <svg ref={svgRef} style={{ width:'100%', height:'520px', display:'block' }}/>
          {tooltip && (
            <div style={{ position:'fixed', left:tooltip.x, top:tooltip.y, background:'rgba(0,0,0,0.85)', color:'#fff', borderRadius:'6px', padding:'8px 12px', fontSize:'12px', pointerEvents:'none', zIndex:9999, maxWidth:'240px' }}>
              <div style={{ fontWeight:700 }}>{tooltip.name}</div>
              {tooltip.rev  && <div>Rev: {tooltip.rev}</div>}
              {tooltip.type && <div>Type: {tooltip.type}</div>}
              <div style={{ fontSize:'11px', color:LAYER_DEF[tooltip.layer].color, marginTop:'3px', fontWeight:700 }}>{LAYER_DEF[tooltip.layer].label}</div>
            </div>
          )}
          <div style={{ position:'absolute', bottom:'10px', left:'10px', display:'flex', gap:'6px', flexWrap:'wrap' }}>
            {Object.entries(LAYER_DEF).filter(([k])=>!hiddenLayers.has(k)).map(([k,def])=>(
              <span key={k} style={{ display:'inline-flex', alignItems:'center', gap:'4px', padding:'2px 8px', background:'rgba(255,255,255,0.9)', borderRadius:'10px', fontSize:'10px', fontWeight:700, border:`1px solid ${def.color}40` }}>
                <span style={{ width:8, height:8, borderRadius:'50%', background:def.color, display:'inline-block' }}/>
                {def.label}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Main shell ─────────────────────────────────────────────────────────────────
const TOOLS = [
  { id:'traceability', Icon:GitBranch,      label:'BOM Traceability',  desc:'Search & explore EBOM / MBOM / BOP hierarchy'   },
  { id:'comparison',   Icon:ArrowLeftRight, label:'BOM Comparison',    desc:'Search two BOMs and diff key values side-by-side' },
  { id:'graph',        Icon:Network,        label:'Traceability Graph', desc:'Force-directed graph with EBOM / MBOM / BOP / STEP CAD layer toggles' },
];

export default function TraceabilityTools() {
  const [activeTool, setActiveTool] = useState('traceability');
  const tool = TOOLS.find(t => t.id === activeTool);

  return (
    <div style={{ background:C.bg, boxSizing:'border-box', minHeight:'calc(100vh - 180px)', padding:'20px 24px' }}>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <div style={{ display:'flex', alignItems:'center', gap:'12px', marginBottom:'18px', flexWrap:'wrap' }}>
        <div style={{ display:'flex', background:C.surface, border:`1px solid ${C.border}`, borderRadius:'8px', padding:'3px', gap:'2px', boxShadow:'0 1px 4px rgba(0,0,0,0.06)' }}>
          {TOOLS.map(t=>{
            const active=activeTool===t.id;
            return (
              <button key={t.id} onClick={()=>setActiveTool(t.id)}
                style={{ display:'flex', alignItems:'center', gap:'7px', padding:'7px 16px', border:'none', borderRadius:'6px', cursor:'pointer', background:active?C.primary:'transparent', color:active?'#fff':C.textSec, fontWeight:active?700:500, fontSize:'13px', transition:'all .15s' }}>
                <t.Icon size={14} strokeWidth={2.5}/>{t.label}
              </button>
            );
          })}
        </div>
        <span style={{ fontSize:'12px', color:C.textSec }}>{tool.desc}</span>
        <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:'5px', background:C.primaryLight, border:`1px solid ${C.primary}30`, borderRadius:'20px', padding:'4px 12px', fontSize:'11px', color:C.primary, fontWeight:600 }}>
          <Info size={11}/> Live data from Neo4j knowledge graph
        </div>
      </div>
      <div style={{ borderBottom:`2px solid ${C.border}`, marginBottom:'18px' }}/>
      {activeTool==='traceability' && <TraceabilityView/>}
      {activeTool==='comparison'   && <BOMComparison/>}
      {activeTool==='graph'        && <TraceabilityGraph/>}
    </div>
  );
}
