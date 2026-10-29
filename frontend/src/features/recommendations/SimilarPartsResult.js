import { CARD, TH, TD, TABLE, Badge, SimilarityBar, ResultTabBar } from "./RecommendationPrimitives.js";
import React, { useState } from "react";
import { Search, Info } from "lucide-react";
import { UI_COLORS as C } from "../../styles/uiTokens";

const SimilarPartsResult = ({ data }) => {
  const [tab, setTab] = useState('overview');
  if (data.message && !data.source_part) {
    return <div style={CARD}><em style={{ color: C.textSec }}>{data.message}</em></div>;
  }

  const sp = data.source_part || {};
  const tabs = [
    { id: 'overview', label: 'Overview',       color: C.primaryText },
    { id: 'results',  label: 'Similar Parts',   color: C.primaryText, count: data.similar_parts?.length || 0 },
  ];

  return (
    <div>
      {/* Header Ã¢â‚¬â€ always visible */}
      <div style={CARD}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <Search size={17} color={C.primary} strokeWidth={2.5} />
          <span style={{ fontSize: '15px', fontWeight: 700, color: C.textPrimary }}>
            Similar parts to: <span style={{ color: C.primaryText }}>{sp.name}</span>
          </span>
        </div>
        <div>
          <Badge color={C.primary}>{sp.source_tag}</Badge>
          {sp.rflp_layer && <Badge color={C.textSec}>{sp.rflp_layer}</Badge>}
          <span style={{ marginLeft: '10px', fontSize: '13px', color: C.textSec }}>{data.similar_parts?.length || 0} results</span>
        </div>
      </div>

      {data.coverage?.limit_reached && <p role="status">The candidate limit was reached. Ranking covers only the inspected candidate slice; narrow the ontology scope before deciding on reuse.</p>}
      {data.ranking_scope && <p>{data.ranking_scope}</p>}
      <ResultTabBar tabs={tabs} active={tab} onChange={setTab}>

      {tab === 'overview' && (
        <div style={CARD}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
            <div style={{ padding: '14px', borderRadius: '8px', background: C.primaryLight, textAlign: 'center' }}>
              <div style={{ fontSize: '28px', fontWeight: 800, color: C.primaryText }}>{data.similar_parts?.length || 0}</div>
              <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase', fontWeight: 600 }}>Candidates found</div>
            </div>
            <div style={{ padding: '14px', borderRadius: '8px', background: C.bg, textAlign: 'center' }}>
              <div style={{ fontSize: '28px', fontWeight: 800, color: C.orange }}>
                {data.similar_parts?.some(p => typeof p.shared_assembly === 'boolean') ? data.similar_parts.filter(p => p.shared_assembly).length : 'Not assessed'}
              </div>
              <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase', fontWeight: 600 }}>Shared assembly</div>
            </div>
            <div style={{ padding: '14px', borderRadius: '8px', background: C.bg, textAlign: 'center' }}>
              <div style={{ fontSize: '28px', fontWeight: 800, color: C.green }}>
                {data.similar_parts?.filter(p => p.type_match ?? p.score_evidence?.graph_type_match).length || 0}
              </div>
              <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase', fontWeight: 600 }}>Type match</div>
            </div>
          </div>
        </div>
      )}

      {tab === 'results' && (
        data.similar_parts?.length > 0 ? (
          <div style={CARD}>
            <table style={TABLE}>
              <thead><tr><th style={TH}>Part</th><th style={TH}>Match score</th><th style={TH}>Engineering review</th><th style={TH}>Assessed properties</th><th style={TH}>Comparison evidence</th></tr></thead>
              <tbody>{data.similar_parts.map((p,i)=><tr key={p.node_id || i}>
                <td style={TD}>{p.name}</td>
                <td style={TD}><SimilarityBar score={p.similarity_score}/></td>
                <td style={TD}>{p.conflicts?.length ? `Conflicts: ${p.conflicts.join(', ')}` : 'Review required; substitution is not approved'}</td>
                <td style={TD}>{p.score_evidence?.engineering_assessed ?? 0} of {p.engineering_comparisons?.length ?? 0}</td>
                <td style={TD}><details><summary>Review properties and missing evidence</summary><p>{p.comparison_basis}</p>
                  {p.engineering_comparisons?.length ? <table style={TABLE}><thead><tr><th style={TH}>Property</th><th style={TH}>Reference part</th><th style={TH}>Candidate</th><th style={TH}>Finding</th></tr></thead><tbody>{p.engineering_comparisons.map(item=><tr key={item.property}><td style={TD}>{item.property}</td><td style={TD}>{Array.isArray(item.source) ? item.source.join('; ') || 'Not recorded' : 'Not recorded'}</td><td style={TD}>{Array.isArray(item.candidate) ? item.candidate.join('; ') || 'Not recorded' : 'Not recorded'}</td><td style={TD}>{item.status}: {item.reason}</td></tr>)}</tbody></table> : <p>Not assessed</p>}
                  <p>Assembly compatibility: {p.shared_assembly == null ? 'Not assessed' : String(p.shared_assembly)}. RFLP compatibility: {p.rflp_layer_match == null ? 'Not assessed' : String(p.rflp_layer_match)}. Traceability: {p.traceability_link || 'Not assessed'}.</p>
                </details></td>
              </tr>)}</tbody>
            </table>
          </div>
        ) : (
          <div style={{ ...CARD, textAlign: 'center', padding: '36px' }}>
            <Info size={28} color={C.textMuted} style={{ display: 'block', margin: '0 auto 10px' }} />
            <div style={{ color: C.textSec }}>No matches found.</div>
          </div>
        )
      )}
      </ResultTabBar>
    </div>
  );
};

export { SimilarPartsResult };
