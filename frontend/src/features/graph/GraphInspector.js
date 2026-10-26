import React from 'react';
import { UI_COLORS } from '../../styles/uiTokens';
import DecisionPolicyAssessment from '../../Components/DecisionPolicyAssessment';

const _PILL = (c) => ({ display: 'inline-block', padding: '2px 8px', borderRadius: '10px', fontSize: '11px', fontWeight: 600, background: c, color: '#fff', marginRight: '4px', marginBottom: '3px' });

const _ROW  = { padding: '6px 0', borderBottom: '1px solid #f0f0f0', fontSize: '12px' };

function RecPanelResult({ service, data, setRecPanel, setActiveTab }) {
  const viewBtn = (names, ids = []) => (
    <button
      onClick={() => { window.dispatchEvent(new CustomEvent('dt-highlight-nodes', { detail: ids.filter(Boolean).length ? {ids:ids.filter(Boolean)} : {names} })); setRecPanel(p => ({ ...p, open: false })); }}
      style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '4px 10px', border: `1px solid ${UI_COLORS.primary}`, borderRadius: '5px', background: UI_COLORS.primaryLight, color: UI_COLORS.primaryText, fontSize: '11px', fontWeight: 600, cursor: 'pointer', marginTop: '8px' }}
    >
      Highlight in graph
    </button>
  );

  if (service === 'change-impact') {
    const ce = data.change_entity;
    if (!ce) return <div role="status" style={{ color: '#7f8c8d' }}>{data.message || 'No entity found'}</div>;
    const allNames = [ce.name, ...(data.impacted_parts || []).map(p => p.name), ...(data.assembly_impact || []).map(a => a.assembly_name)].filter(Boolean);
    return (
      <div>
        {data.message && <p role="status">{data.message}</p>}
        {data.coverage?.limit_reached && <p>Traversal limit reached; further dependency review is required.</p>}
        {(data.realization_chain || []).slice(0,8).map(item=><p key={item.node_id}>{item.path_names?.join(' → ')}{item.review_status === 'configuration_conflict' ? ' · Configuration conflict' : ''}</p>)}
        {typeof data.impact_score === 'number' && Number.isFinite(data.impact_score) && <div style={{ fontWeight: 700, marginBottom: '8px' }}>Linked evidence indicator: {data.impact_score}/100 <small>(heuristic)</small></div>}
        {data.impacted_parts?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Impacted Parts ({data.impacted_parts.length})</strong>{data.impacted_parts.slice(0, 8).map((p, i) => <div key={i} style={_ROW}><span style={_PILL('#3498db')}>{p.source_tag || '?'}</span> {p.name}</div>)}</div>}
        {data.assembly_impact?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Assemblies ({data.assembly_impact.length})</strong>{data.assembly_impact.slice(0, 6).map((a, i) => <div key={i} style={_ROW}>{a.assembly_name} <em style={{ color: '#999' }}>depth {a.depth}</em></div>)}</div>}
        {data.process_impacts?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Processes ({data.process_impacts.length})</strong></div>}
        {data.realization_chain?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Realization ({data.realization_chain.length})</strong></div>}
        {allNames.length > 0 && viewBtn(allNames,[ce.node_id,...(data.realization_chain || []).map(item=>item.node_id)])}
      </div>
    );
  }
  if (service === 'similar-parts') {
    if (!data.source_part) return <div style={{ color: '#7f8c8d' }}>Not found</div>;
    const allNames = [data.source_part.name, ...(data.similar_parts || []).map(p => p.name)].filter(Boolean);
    return (
      <div>
        <div style={{ fontWeight: 700, marginBottom: '8px' }}>{data.similar_parts?.length || 0} similar parts</div>
        {(data.similar_parts || []).slice(0, 10).map((p, i) => (
          <div key={i} style={_ROW}>
            <strong>{p.name}</strong> \u2014 <span style={{ color: UI_COLORS.primaryText, fontWeight: 600 }}>{p.similarity_score}</span>
            <p>{p.conflicts?.length ? `Conflicts: ${p.conflicts.join(', ')}` : 'Engineering review required'} · {p.score_evidence?.engineering_assessed ?? 0} properties assessed</p>
            {p.shared_assembly && <span style={_PILL('#27ae60')}>Assembly</span>}
            {p.traceability_link && <span style={_PILL('#e67e22')}>{p.traceability_link}</span>}
          </div>
        ))}
        {allNames.length > 1 && viewBtn(allNames,[data.source_part.node_id,...(data.similar_parts || []).map(item=>item.node_id)])}
      </div>
    );
  }
  if (service === 'manufacturing') {
    if (!data.part) return <div style={{ color: '#7f8c8d' }}>Not found</div>;
    const allNames = [data.part.name, ...(data.direct_processes || []).map(p => p.process_name), ...(data.process_instances || []).map(p => p.name)].filter(Boolean);
    return (
      <div>
        {data.direct_processes?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Direct ({data.direct_processes.length})</strong>{data.direct_processes.slice(0, 6).map((p, i) => <div key={i} style={_ROW}><span style={_PILL(UI_COLORS.primary)}>{p.source_tag || '?'}</span> {p.process_name}</div>)}</div>}
        {data.process_instances?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Instances ({data.process_instances.length})</strong>{data.process_instances.slice(0, 6).map((p, i) => <div key={i} style={_ROW}>{p.name}</div>)}</div>}
        {data.related_part_processes?.length > 0 && <div style={{ marginBottom: '8px' }}><strong>Related ({data.related_part_processes.length})</strong></div>}
        {allNames.length > 1 && viewBtn(allNames)}
      </div>
    );
  }
  return null;
}

export default function GraphInspector({ recPanel, setRecPanel, setActiveTab }) {
  return (recPanel.open && (
        <div style={{
          position: 'absolute', top: 0, right: 0, width: 'min(380px, 100%)', height: '100%',
          background: '#fff', boxShadow: '-4px 0 16px rgba(0,0,0,0.12)',
          zIndex: 3000, display: 'flex', flexDirection: 'column',
          borderLeft: `2px solid ${UI_COLORS.primary}`, borderRadius: '0 0 0 8px',
          animation: 'slideInRight 0.25s ease-out',
        }}>
          {/* Panel header */}
          <div style={{
            padding: '12px 16px', background: `linear-gradient(135deg, ${UI_COLORS.primary} 0%, ${UI_COLORS.primaryDark || '#003f73'} 100%)`,
            color: '#fff', display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}>
            <div style={{ fontWeight: 700, fontSize: '14px' }}>
              {recPanel.service === 'change-impact' ? 'Change Impact' :
               recPanel.service === 'similar-parts' ? '[FIND] Similar Parts' : '[MFG] Manufacturing'}
            </div>
            <button type="button" aria-label="Close graph inspector" onClick={() => setRecPanel({ open: false, service: null, nodeName: '', loading: false, result: null, error: '' })}
              style={{ background: 'none', border: 'none', color: '#fff', fontSize: '18px', cursor: 'pointer', padding: '0 4px' }}>&times;</button>
          </div>
          {/* Panel body */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '12px', fontSize: '13px' }}>
            <div style={{ color: '#7f8c8d', marginBottom: '10px' }}>
              Node: <strong style={{ color: '#2c3e50' }}>{recPanel.nodeName}</strong>
            </div>
            <a href="#/recommendations" onClick={()=>{
              const selected=recPanel.context || {};
              window.__dt_rec_prefill={service:recPanel.service,nodeName:recPanel.nodeName,
                node_id:selected.nodeId || recPanel.result?.source_part?.node_id || recPanel.result?.change_entity?.node_id,
                ontology_id:selected.ontologyId,ontology_prefix:selected.ontologyPrefix};
            }}>Open full engineering review</a>
            {recPanel.loading && (
              <div style={{ textAlign: 'center', padding: '40px 0', color: '#7f8c8d' }}>
                <div style={{ width: 28, height: 28, border: '3px solid #eee', borderTop: `3px solid ${UI_COLORS.primary}`, borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 10px' }} />
                Analysing...
              </div>
            )}
            {recPanel.error && <div style={{ color: '#e74c3c', padding: '10px', background: '#fdf2f2', borderRadius: '6px' }}>{recPanel.error}</div>}
            {recPanel.result && <><DecisionPolicyAssessment report={recPanel.result.decision_policy}/><RecPanelResult service={recPanel.service} data={recPanel.result} setRecPanel={setRecPanel} setActiveTab={setActiveTab} /></>}
          </div>
        </div>
      ));
}
