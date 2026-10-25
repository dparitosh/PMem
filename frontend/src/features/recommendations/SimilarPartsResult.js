import { CARD, TH, TD, TABLE, Badge, SimilarityBar, CheckCell, ResultTabBar } from "./RecommendationPrimitives.js";
import React, { useState } from "react";
import { Search, Minus, Info } from "lucide-react";
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

      <ResultTabBar tabs={tabs} active={tab} onChange={setTab} />

      {tab === 'overview' && (
        <div style={CARD}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
            <div style={{ padding: '14px', borderRadius: '8px', background: C.primaryLight, textAlign: 'center' }}>
              <div style={{ fontSize: '28px', fontWeight: 800, color: C.primaryText }}>{data.similar_parts?.length || 0}</div>
              <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase', fontWeight: 600 }}>Candidates found</div>
            </div>
            <div style={{ padding: '14px', borderRadius: '8px', background: C.bg, textAlign: 'center' }}>
              <div style={{ fontSize: '28px', fontWeight: 800, color: C.orange }}>
                {data.similar_parts?.filter(p => p.shared_assembly).length || 0}
              </div>
              <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase', fontWeight: 600 }}>Shared assembly</div>
            </div>
            <div style={{ padding: '14px', borderRadius: '8px', background: C.bg, textAlign: 'center' }}>
              <div style={{ fontSize: '28px', fontWeight: 800, color: C.green }}>
                {data.similar_parts?.filter(p => p.source_tag_match).length || 0}
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
              <thead><tr>
                <th style={TH}>Part Name</th>
                <th style={TH}>Score</th>
                <th style={TH}>Type Match</th>
                <th style={TH}>RFLP Match</th>
                <th style={TH}>Assembly</th>
                <th style={TH}>Traceability</th>
              </tr></thead>
              <tbody>
                {data.similar_parts.map((p, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? C.surface : C.bg }}>
                    <td style={TD}><span style={{ fontWeight: 700, color: C.primaryText }}>{p.name}</span></td>
                    <td style={TD}><SimilarityBar score={p.similarity_score} /></td>
                    <td style={TD}><CheckCell value={p.source_tag_match} /></td>
                    <td style={TD}><CheckCell value={p.rflp_layer_match} /></td>
                    <td style={TD}><CheckCell value={p.shared_assembly} /></td>
                    <td style={TD}>{p.traceability_link ? <Badge color={C.orange}>{p.traceability_link}</Badge> : <Minus size={13} color={C.textMuted} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ ...CARD, textAlign: 'center', padding: '36px' }}>
            <Info size={28} color={C.textMuted} style={{ display: 'block', margin: '0 auto 10px' }} />
            <div style={{ color: C.textSec }}>No matches found.</div>
          </div>
        )
      )}
    </div>
  );
};

export { SimilarPartsResult };
