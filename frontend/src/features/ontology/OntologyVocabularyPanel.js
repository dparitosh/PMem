import { RelBadge, relationPlainName } from "./OntologyRelationBadge.js";
import { exportCSV } from "../../shared/components/ontologyTablePrimitives";
import React, { useState, useEffect, useMemo, useRef } from "react";
import { Download } from "../../ui/IxIcons";
import { ixIconName } from "../../ui/ixIconRegistry";
import { EmptyState, PrimaryButton } from "../../ui/ix";
import "./OntologyVocabularyPanel.css";

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
    <div className="vocab-panel">
      <div className="vocab-panel__toolbar">
        <div className="vocab-panel__relations">
          <span className="vocab-panel__relations-label">Relation types:</span>
          <button type="button" className="vocab-panel__chip" aria-pressed={!relationFilter} onClick={() => setRelationFilter('')}>All relations</button>
          {Object.entries(typeGroups).map(([type, count]) => (
            <button
              type="button"
              className="vocab-panel__chip"
              aria-pressed={relationFilter === type}
              title={type}
              onClick={() => setRelationFilter(relationFilter === type ? '' : type)}
              key={type}
            >
              {relationPlainName(type)}
              <span className="vocab-panel__chip-count">({count})</span>
            </button>
          ))}
        </div>
        <div className="vocab-panel__actions">
          <span className="vocab-panel__count">{visible.length} of {edges.length} mappings</span>
          <PrimaryButton
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
          ><Download size={12} /> Export CSV</PrimaryButton>
        </div>
      </div>
      {truncated && <p role="status">Only the first returned mappings are shown. Counts and CSV export cover this subset.</p>}
      <p className="vocab-panel__help">Domain, range and subclass relations describe ontology structure; exact and close matches describe vocabulary alignment. Select a relation type to filter.</p>
      {visible.length === 0 ? (
        <EmptyState
          icon={ixIconName.search}
          title="No mappings match this filter"
          body="Clear the relation type or change the search text to see more mappings."
          action={relationFilter ? { label: 'Show all relations', onClick: () => setRelationFilter('') } : undefined}
        />
      ) : (
      <div ref={tableScroll} className="vocab-panel__table-wrap">
        <table className="vocab-panel__table">
          <thead>
            <tr>
              <th scope="col" className="vocab-panel__th vocab-panel__th--index">#</th>
              <th scope="col" className="vocab-panel__th">Source Concept</th>
              <th scope="col" className="vocab-panel__th vocab-panel__th--relation">Relation</th>
              <th scope="col" className="vocab-panel__th">Target Concept</th>
            </tr>
          </thead>
          <tbody>
            {pageRows.map((e, i) => {
              const rowId = `${e.source_term}__${e.mapping_type}__${e.target_term}`;
              const selected = selectedRow === rowId;
              const rowClass = ['vocab-panel__row', i % 2 === 1 ? 'vocab-panel__row--alt' : '', selected ? 'vocab-panel__row--selected' : ''].filter(Boolean).join(' ');
              return (
                <React.Fragment key={e.source_term + '-' + e.mapping_type + '-' + e.target_term}>
                  <tr
                    tabIndex={0}
                    aria-expanded={selected}
                    onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setSelectedRow(selected ? null : rowId); } }}
                    onClick={() => setSelectedRow(selected ? null : rowId)}
                    className={rowClass}
                  >
                    <td className="vocab-panel__td vocab-panel__td--index">{offset + i + 1}</td>
                    <td className="vocab-panel__td">
                      <div className="vocab-panel__label">{e.source_label || e.source_term.split(':').pop()}</div>
                      <div className="vocab-panel__term-id">{e.source_term}</div>
                    </td>
                    <td className="vocab-panel__td vocab-panel__td--relation" title={e.mapping_type}>
                      <span>{relationPlainName(e.mapping_type)}</span>
                    </td>
                    <td className="vocab-panel__td">
                      <div className="vocab-panel__label">{e.target_label || e.target_term.split(':').pop()}</div>
                      <div className="vocab-panel__term-id">{e.target_term}</div>
                    </td>
                  </tr>
                  {selected && (
                    <tr className="vocab-panel__row--selected">
                      <td colSpan={4} className="vocab-panel__detail">
                        <div className="vocab-panel__detail-grid">
                          <div>
                            <div className="vocab-panel__detail-heading">Source</div>
                            <div className="vocab-panel__detail-name">{e.source_label || e.source_term.split(':').pop()}</div>
                            <code className="vocab-panel__detail-code">{e.source_term}</code>
                          </div>
                          <div className="vocab-panel__detail-middle">
                            <RelBadge type={e.mapping_type} />
                            <div className="vocab-panel__arrow">→</div>
                          </div>
                          <div>
                            <div className="vocab-panel__detail-heading">Target</div>
                            <div className="vocab-panel__detail-name">{e.target_label || e.target_term.split(':').pop()}</div>
                            <code className="vocab-panel__detail-code">{e.target_term}</code>
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
      )}
      <nav aria-label="Mapping pagination" className="vocab-panel__pagination">
        <label>Mappings per page{' '}
          <select className="vocab-panel__page-size" value={pageSize} onChange={event => setPageSize(Number(event.target.value))}>
            {[25, 50, 100].map(size => <option key={size} value={size}>{size}</option>)}
          </select>
        </label>
        <span role="status">{visible.length ? `${offset + 1}–${Math.min(offset + pageSize, visible.length)} of ${visible.length} mappings` : '0 mappings'}</span>
        <div className="vocab-panel__pager">
          <button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button>
          <span>Page {currentPage + 1} of {pageCount}</span>
          <button type="button" disabled={currentPage + 1 >= pageCount} onClick={() => setPage(currentPage + 1)}>Next</button>
        </div>
      </nav>
    </div>
  );
}

export { VocabularyTable };
