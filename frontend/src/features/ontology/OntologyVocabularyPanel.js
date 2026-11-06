import { RelBadge } from "./OntologyRelationBadge.js";
import { exportCSV, TH, TD } from "../../shared/components/ontologyTablePrimitives";
import React, { useState, useEffect, useMemo, useRef } from "react";
import { Download } from "lucide-react";
import { UI_COLORS as C } from "../../styles/uiTokens";

function VocabularyTable({ edges, filter, truncated = false }) {
  const [relationFilter, setRelationFilter] = useState('');
  const [selectedRow, setSelectedRow] = useState(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const tableScroll = useRef(null);
  useEffect(() => { if (relationFilter && !edges.some(edge => edge.mapping_type === relationFilter)) setRelationFilter(''); }, [edges, relationFilter]);
  const lc = filter.toLowerCase();
  const visible = useMemo(() => {
    return edges.filter(e => {
      if (relationFilter && e.mapping_type !== relationFilter) return false;
      if (!lc) return true;
      return (
        e.source_term.toLowerCase().includes(lc) ||
        e.target_term.toLowerCase().includes(lc) ||
        e.mapping_type.toLowerCase().includes(lc) ||
        (e.source_label || '').toLowerCase().includes(lc) ||
        (e.target_label || '').toLowerCase().includes(lc)
      );
    });
  }, [edges, lc, relationFilter]);

  const pageCount = Math.max(1, Math.ceil(visible.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  const offset = currentPage * pageSize;
  const pageRows = visible.slice(offset, offset + pageSize);
  useEffect(() => { setPage(0); setSelectedRow(null); }, [edges, lc, pageSize, relationFilter]);
  useEffect(() => {
    setSelectedRow(null);
    if (tableScroll.current) tableScroll.current.scrollTop = 0;
  }, [currentPage, edges, lc, pageSize]);

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
          <button type="button" aria-pressed={!relationFilter} onClick={() => setRelationFilter('')}>All relations</button>
          {Object.entries(typeGroups).map(([type, count]) => (
            <button type="button" aria-pressed={relationFilter === type} onClick={() => setRelationFilter(relationFilter === type ? '' : type)} key={type} style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
              <RelBadge type={type} />
              <span style={{ fontSize: '11px', color: C.textMuted }}>({count})</span>
            </button>
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
      {truncated && <p role="status">Only the first returned mappings are shown. Counts and CSV export cover this subset.</p>}
      <p>Domain, range and subclass relations describe ontology structure; exact and close matches describe vocabulary alignment. Select a relation type to filter.</p>
      <div ref={tableScroll} style={{ border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'auto', maxHeight: '520px' }}>
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
            {pageRows.map((e, i) => {
              const rowId = `${e.source_term}__${e.mapping_type}__${e.target_term}`;
              const selected = selectedRow === rowId;
              return (
                <React.Fragment key={e.source_term + '-' + e.mapping_type + '-' + e.target_term}>
                  <tr
                    tabIndex={0}
                    aria-expanded={selected}
                    onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedRow(selected ? null : rowId); } }}
                    onClick={() => setSelectedRow(selected ? null : rowId)}
                    style={{ background: selected ? C.primaryLight : i % 2 === 0 ? C.surface : C.bg, cursor: 'pointer' }}
                    onMouseEnter={ev => { if (!selected) ev.currentTarget.style.background = C.primaryLight; }}
                    onMouseLeave={ev => { if (!selected) ev.currentTarget.style.background = i % 2 === 0 ? C.surface : C.bg; }}
                  >
                    <td style={TD({ textAlign: 'center', color: C.textMuted, fontSize: '11px' })}>{offset + i + 1}</td>
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
                    <tr style={{ background: C.primaryLight }}>
                      <td colSpan={4} style={{ padding: '12px 20px', borderBottom: `1px solid ${C.border}` }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: '16px', alignItems: 'start' }}>
                          <div>
                            <div style={{ fontSize: '11px', fontWeight: 700, color: C.textSec, textTransform: 'uppercase', marginBottom: '4px' }}>Source</div>
                            <div style={{ fontWeight: 700, color: C.primaryText }}>{e.source_label || e.source_term.split(':').pop()}</div>
                            <code style={{ fontSize: '11px', color: C.textSec, wordBreak: 'break-all' }}>{e.source_term}</code>
                          </div>
                          <div style={{ textAlign: 'center', paddingTop: '10px' }}>
                            <RelBadge type={e.mapping_type} />
                            <div style={{ fontSize: '18px', color: C.textMuted, marginTop: '4px' }}>Ã¢â€ â€™</div>
                          </div>
                          <div>
                            <div style={{ fontSize: '11px', fontWeight: 700, color: C.textSec, textTransform: 'uppercase', marginBottom: '4px' }}>Target</div>
                            <div style={{ fontWeight: 700, color: C.primaryText }}>{e.target_label || e.target_term.split(':').pop()}</div>
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
      <nav aria-label="Mapping pagination" style={{ display: 'flex', flexWrap: 'wrap', gap: 12, alignItems: 'center', justifyContent: 'space-between', padding: '12px 0' }}>
        <label>Mappings per page{' '}
          <select value={pageSize} onChange={event => setPageSize(Number(event.target.value))}>
            {[25, 50, 100].map(size => <option key={size} value={size}>{size}</option>)}
          </select>
        </label>
        <span role="status">{visible.length ? `${offset + 1}–${Math.min(offset + pageSize, visible.length)} of ${visible.length} mappings` : '0 mappings'}</span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', whiteSpace: 'nowrap' }}>
          <button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button>
          <span>Page {currentPage + 1} of {pageCount}</span>
          <button type="button" disabled={currentPage + 1 >= pageCount} onClick={() => setPage(currentPage + 1)}>Next</button>
        </div>
      </nav>
    </div>
  );
}

export { VocabularyTable };
