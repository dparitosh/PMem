import { exportCSV, TH, TD } from '../../shared/components/ontologyTablePrimitives';
import { requirementsPayload } from "../../services/pagePayloads";
import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { Upload, FileText, Download } from "lucide-react";
import { API_METHODS } from "../../services/apiClient";
import { apiErrorMessage } from "../../utils/apiErrorMessage";
import { UI_COLORS as C } from "../../styles/uiTokens";

export default function RequirementsWorkbench({ filter = "", onNavigate }) {
  const [graphRequirements, setGraphRequirements] = useState([]);
  const [graphLoading, setGraphLoading] = useState(false);
  const [graphError, setGraphError] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [requirementOffset, setRequirementOffset] = useState(0);
  const [requirementsHaveMore, setRequirementsHaveMore] = useState(false);
  const requirementRequest = useRef(0);
  const q = String(filter || '').trim().toLowerCase();

  const loadGraphRequirements = useCallback(async () => {
    const requestId = ++requirementRequest.current;
    setGraphLoading(true);
    setGraphError('');
    try {
      const response = await API_METHODS.requirements.list({ source: sourceFilter, limit: 1000, offset: requirementOffset });
      if (requestId !== requirementRequest.current) return;
      setGraphRequirements(requirementsPayload(response?.data?.requirements));
      setRequirementsHaveMore(response?.data?.has_more === true);
    } catch (err) {
      if (requestId !== requirementRequest.current) return;
      setGraphError(apiErrorMessage(err, 'Unable to load graph requirements.'));
      setGraphRequirements([]);
      setRequirementsHaveMore(false);
    } finally {
      if (requestId === requirementRequest.current) setGraphLoading(false);
    }
  }, [sourceFilter, requirementOffset]);

  useEffect(() => {
    loadGraphRequirements();
    return () => { requirementRequest.current += 1; };
  }, [loadGraphRequirements]);

  useEffect(() => {
    const refresh = () => loadGraphRequirements();
    window.addEventListener('depo:credentials-changed', refresh);
    window.addEventListener('depo:credentials-cleared', refresh);
    return () => {
      window.removeEventListener('depo:credentials-changed', refresh);
      window.removeEventListener('depo:credentials-cleared', refresh);
    };
  }, [loadGraphRequirements]);

  const graphRequirementRows = useMemo(() => (graphRequirements || []).map((row) => ({
    id: row.requirement_id || row.id || row.element_id,
    title: row.title || row.requirement_id || row.id,
    description: row.text || '',
    typeRef: row.semantic_role || row.ontology_class || '',
    source: row.source || 'Graph',
    sourceFile: row.source_file || '',
    status: row.status || '',
    ontologyClass: row.ontology_class || row.labels?.[0] || '',
    relationshipCount: row.relationship_count || 0,
    contextText: (row.context_links || []).map((item) => `${item.type}: ${item.other}`).join(' | '),
  })), [graphRequirements]);

  const visibleRequirements = useMemo(() => {
    const rows = graphRequirementRows;
    if (!q) return rows;
    return rows.filter((row) => [row.id, row.title, row.description, row.typeRef, row.source, row.sourceFile, row.ontologyClass, row.contextText].some((value) => String(value || '').toLowerCase().includes(q)));
  }, [graphRequirementRows, q]);

  const openImport = () => {
    if (typeof onNavigate === 'function') onNavigate('import');
  };

  const exportRows = () => {
    exportCSV(
      visibleRequirements.map((row) => ({
        ID: row.id,
        Source: row.source || 'Graph',
        Title: row.title,
        Description: row.description,
        Type: row.typeRef || row.ontologyClass || '',
        Attributes: row.contextText || (row.attributes || []).map((a) => `${a.definition}: ${a.value}`).join(' | '),
      })),
      ['ID', 'Source', 'Title', 'Description', 'Type', 'Attributes'],
      'requirements_workbench.csv'
    );
  };

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: '8px', padding: '14px', minHeight: '420px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px', fontWeight: 800, color: C.textPrimary }}><FileText size={16} /> Requirements workbench</div>
          <div style={{ fontSize: '12px', color: C.textSec, marginTop: '3px' }}>View normalized requirements from Neo4j context graph plus uploaded ReqIF 1.2 files for Semantic Bridge, GraphRAG, and traceability review.</div>
        </div>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <select aria-label="Requirement source filter" value={sourceFilter} onChange={(event) => { setSourceFilter(event.target.value); setRequirementOffset(0); }} style={{ padding: '7px 10px', borderRadius: '6px', border: `1px solid ${C.borderDark}`, background: C.surface, color: C.textPrimary, fontSize: '12px', fontWeight: 700 }}>
            {['all', 'ReqIF', 'PLMXML', 'MBSE', 'OSLC', 'ALM', 'Unstructured', 'Graph'].map((source) => <option key={source} value={source}>{source === 'all' ? 'All graph sources' : source}</option>)}
          </select>
          <button type="button" onClick={loadGraphRequirements} disabled={graphLoading} style={{ padding: '7px 12px', borderRadius: '6px', border: `1px solid ${C.borderDark}`, background: C.surface, color: C.primaryDark, fontSize: '12px', fontWeight: 800, cursor: graphLoading ? 'wait' : 'pointer' }}>{graphLoading ? 'Loading graph' : 'Refresh graph'}</button>
          <button type="button" onClick={openImport} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '7px 12px', borderRadius: '6px', border: `1px solid ${C.primary}`, background: C.primary, color: '#fff', fontSize: '12px', fontWeight: 800, cursor: 'pointer' }}>
            <Upload size={13} /> Open Import
          </button>
          <button type="button" onClick={exportRows} disabled={visibleRequirements.length === 0} style={{ padding: '7px 12px', borderRadius: '6px', border: `1px solid ${C.borderDark}`, background: visibleRequirements.length ? C.surface : C.bg, color: visibleRequirements.length ? C.primaryDark : C.textMuted, fontSize: '12px', fontWeight: 800, cursor: visibleRequirements.length ? 'pointer' : 'not-allowed' }}><Download size={13} /> CSV</button>
        </div>
      </div>

      {graphError && <div style={{ marginBottom: '12px', padding: '9px 12px', borderRadius: '6px', border: `1px solid #F7C948`, background: '#FFF8E1', color: '#7A4E00', fontSize: '12px', fontWeight: 700 }}>{graphError}</div>}

      <div style={{ display: 'grid', gap: '12px' }}>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {[
              ['Graph requirements', graphRequirementRows.length],
              ['Visible', visibleRequirements.length],
              ['Source', 'Import pipeline'],
            ].map(([label, value]) => (
              <div key={label} style={{ padding: '6px 10px', borderRadius: '999px', border: `1px solid ${C.border}`, background: C.bg, fontSize: '11px', fontWeight: 800, color: C.textPrimary }}>{label}: {value}</div>
            ))}
          </div>
          <div style={{ padding: '8px 10px', borderRadius: '6px', background: '#EEF7FF', border: `1px solid ${C.border}`, fontSize: '11px', color: C.textPrimary }}>
            Source: Neo4j graph loaded through the Import pipeline. Use Import for ReqIF/PLMXML/MBSE/OSLC/ALM/unstructured ingestion, then review normalized requirements here.
          </div>
          <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'auto', maxHeight: '360px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '860px' }}>
              <thead>
                <tr>
                  <th style={TH({ width: '150px' })}>Requirement ID</th>
                  <th style={TH({ width: '110px' })}>Source</th>
                  <th style={TH({ minWidth: '220px' })}>Title</th>
                  <th style={TH({ minWidth: '300px' })}>Text / Context</th>
                  <th style={TH({ width: '170px' })}>Ontology / Type</th>
                  <th style={TH({ width: '90px', textAlign: 'center' })}>Links</th>
                </tr>
              </thead>
              <tbody>
                {visibleRequirements.length === 0 && <tr><td colSpan={6} style={TD({ textAlign: 'center', padding: '26px', color: C.textMuted })}>No requirements match the current filter or graph source.</td></tr>}
                {visibleRequirements.map((row, idx) => (
                  <tr key={`${row.id}-${idx}`} style={{ background: idx % 2 === 0 ? C.surface : C.bg }}>
                    <td style={TD({ fontFamily: 'monospace', fontWeight: 800, color: C.primaryText })}>{row.id}</td>
                    <td style={TD({ fontWeight: 800, color: C.primaryDark })}>{row.source || 'Graph'}</td>
                    <td style={TD({ fontWeight: 700 })}>{row.title}</td>
                    <td style={TD({ fontSize: '12px', lineHeight: 1.45 })}>
                      {row.description || <span style={{ color: C.textMuted }}>No description text</span>}
                      {row.contextText && <div style={{ marginTop: '5px', color: C.textSec }}>{row.contextText}</div>}
                      {row.sourceFile && <div style={{ marginTop: '5px', color: C.textMuted, fontSize: '11px' }}>{row.sourceFile}</div>}
                    </td>
                    <td style={TD({ fontFamily: 'monospace', fontSize: '11px', color: C.textSec })}>{row.ontologyClass || row.typeRef || 'n/a'}</td>
                    <td style={TD({ textAlign: 'center', fontWeight: 800 })}>{row.relationshipCount || 0}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <button disabled={graphLoading || requirementOffset === 0} onClick={() => setRequirementOffset(Math.max(0, requirementOffset - 1000))}>Previous</button>
            <span>Page {Math.floor(requirementOffset / 1000) + 1}. Search and CSV apply to this page.</span>
            <button disabled={graphLoading || !requirementsHaveMore} onClick={() => setRequirementOffset(requirementOffset + 1000)}>Next</button>
          </div>
        </div>
    </div>
  );
}
