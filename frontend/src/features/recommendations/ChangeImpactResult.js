import DependencyPathGraph from './DependencyPathGraph';
import {businessDisplayName, businessPathNames} from './businessDisplayName';
import { CARD, TH, TD, TABLE, Badge, ScoreBar, ResultTabBar } from "./RecommendationPrimitives.js";
import React, { useState } from "react";
import { Zap } from "lucide-react";
import { UI_COLORS as C } from "../../styles/uiTokens";

const ChangeImpactResult = ({ data }) => {
  const [tab, setTab] = useState('overview');
  if (data.message && !data.change_entity) {
    return <div style={CARD}><em style={{ color: C.textSec }}>{data.message}</em></div>;
  }

  const ce = data.change_entity || {};
  if (data.evidence_status === 'insufficient') {
    return <section aria-label="Change impact evidence" role="status"><h3>{businessDisplayName(ce.name)}</h3><p>{data.message}</p></section>;
  }
  const tabs = [
    { id: 'overview',      label: 'Overview',           color: C.orange  },
    { id: 'parts',         label: 'Impacted Parts',      color: C.orange,  count: data.impacted_parts?.length        || 0 },
    { id: 'assembly',      label: 'Assembly Impact',     color: C.primaryText, count: data.assembly_impact?.length       || 0 },
    { id: 'requirements',  label: 'Requirements',        color: C.amber,   count: data.impacted_requirements?.length || 0 },
    { id: 'processes',     label: 'Processes',           color: C.green,   count: data.process_impacts?.length       || 0 },
    { id: 'realization',   label: 'Realization Chain',   color: C.orange,  count: data.realization_chain?.length     || 0 },
  ];

  return (
    <div>
      {/* Header Ã¢â‚¬â€ always visible */}
      <div style={CARD}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '14px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <Zap size={17} color={C.orange} strokeWidth={2.5} />
              <span style={{ fontSize: '16px', fontWeight: 700, color: C.textPrimary }}>{businessDisplayName(ce.name)}</span>
            </div>
            <div>
              <Badge color={C.red}>{ce.source_tag}</Badge>
              {ce.revision && <Badge color={C.textSec}>Rev {ce.revision}</Badge>}
            </div>
          </div>
          <div style={{ minWidth: '260px' }}>
            <div style={{ fontSize: '11px', color: C.textSec, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '6px' }}>Linked evidence indicator (heuristic)</div>
            {typeof data.impact_score === 'number' && Number.isFinite(data.impact_score) && <ScoreBar score={data.impact_score} />}
            {data.message && <p>{data.message}</p>}
          </div>
        </div>
      </div>

      <section aria-label="Dependency path evidence" style={CARD}>
        <h3>Why these records need review</h3>
        <p>{data.traceability}</p>
        {data.coverage?.limit_reached && <p role="status">The traversal limit was reached. Narrow the selected scope and assess remaining dependencies before approving the change.</p>}
        <table style={TABLE}><thead><tr><th style={TH}>Business record</th><th style={TH}>Dependency path</th><th style={TH}>Configuration and effectivity</th></tr></thead>
          <tbody>{(data.realization_chain || []).map((item,index)=><tr key={item.node_id || index}>
            <td style={TD}>{businessDisplayName(item.name)}<details><summary>Record identity</summary><code>{item.node_id}</code></details></td><td style={TD}>{businessPathNames(item).join(' → ') || item.link_type}
              <details><summary>Path evidence</summary><ol>{(item.path || []).map(edge=><li key={edge.relationship_id}>{edge.predicate || edge.relationship_type} · reference {edge.relationship_id}</li>)}</ol></details>
            </td><td style={TD}>{item.review_status === 'configuration_conflict' ? 'Conflicting configuration evidence; review required' : 'Effectivity review required'}
              {item.configuration_review?.map(entry=><p key={entry.property}>{entry.property}: {Array.isArray(entry.source) ? entry.source.join('; ') || 'Not recorded' : 'Not recorded'} / {Array.isArray(entry.candidate) ? entry.candidate.join('; ') || 'Not recorded' : 'Not recorded'} — {entry.status}</p>)}
            </td></tr>)}</tbody>
        </table>
      </section>

      {/* Result sub-tabs */}
      <ResultTabBar tabs={tabs} active={tab} onChange={setTab}>

      {tab === 'overview' && <DependencyPathGraph data={data} />}

      {tab === 'parts' && (
        data.impacted_parts?.length > 0 ? (
          <div style={CARD}>
            <table style={TABLE}>
              <thead><tr>
                <th style={TH}>Part Name</th><th style={TH}>Type</th><th style={TH}>Relation</th><th style={TH}>Class</th>
              </tr></thead>
              <tbody>
                {data.impacted_parts.map((p, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? C.surface : C.bg }}>
                    <td style={TD}><span style={{ fontWeight: 700, color: C.primaryText }}>{businessDisplayName(p.name)}</span></td>
                    <td style={TD}><Badge color={C.primaryHover}>{p.source_tag || 'Ã¢â‚¬â€'}</Badge></td>
                    <td style={TD}><span style={{ fontWeight: 600, color: C.orange }}>{p.relation_type || 'Ã¢â‚¬â€'}</span></td>
                    <td style={TD}>{p.class_name || 'Ã¢â‚¬â€'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No impacted parts found.</div>
      )}

      {tab === 'assembly' && (
        data.assembly_impact?.length > 0 ? (
          <div style={CARD}>
            <table style={TABLE}>
              <thead><tr>
                <th style={TH}>Assembly</th><th style={TH}>Depth</th><th style={TH}>From Part</th>
              </tr></thead>
              <tbody>
                {data.assembly_impact.map((a, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? C.surface : C.bg }}>
                    <td style={TD}><span style={{ fontWeight: 700, color: C.primaryText }}>{businessDisplayName(a.name || a.assembly_name, 'Assembly name not recorded')}</span></td>
                    <td style={TD}><span style={{ fontWeight: 600, color: C.textSec }}>{a.depth}</span></td>
                    <td style={TD}>{a.from_part || 'Ã¢â‚¬â€'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No assembly impact found.</div>
      )}

      {tab === 'requirements' && (
        data.impacted_requirements?.length > 0 ? (
          <div style={CARD}>
            <table style={TABLE}>
              <thead><tr>
                <th style={TH}>Requirement</th><th style={TH}>Catalogue ID</th><th style={TH}>Linked Part</th>
              </tr></thead>
              <tbody>
                {data.impacted_requirements.map((r, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? C.surface : C.bg }}>
                    <td style={TD}><span style={{ fontWeight: 700, color: C.amber }}>{businessDisplayName(r.name)}</span></td>
                    <td style={TD}><Badge color={C.amber}>{r.catalogue_id || 'Ã¢â‚¬â€'}</Badge></td>
                    <td style={TD}><span style={{ color: C.primaryText, fontWeight: 600 }}>{r.linked_part || 'Ã¢â‚¬â€'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No impacted requirements found.</div>
      )}

      {tab === 'processes' && (
        data.process_impacts?.length > 0 ? (
          <div style={CARD}>
            <table style={TABLE}>
              <thead><tr>
                <th style={TH}>Process</th><th style={TH}>Type</th><th style={TH}>From Part</th>
              </tr></thead>
              <tbody>
                {data.process_impacts.map((p, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? C.surface : C.bg }}>
                    <td style={TD}><span style={{ fontWeight: 700, color: C.green }}>{businessDisplayName(p.name)}</span></td>
                    <td style={TD}><Badge color={C.green}>{p.source_tag || 'Ã¢â‚¬â€'}</Badge></td>
                    <td style={TD}><span style={{ color: C.primaryText, fontWeight: 600 }}>{p.from_part || 'Ã¢â‚¬â€'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No process impacts found.</div>
      )}

      {tab === 'realization' && (
        data.realization_chain?.length > 0 ? (
          <div style={CARD}>
            <table style={TABLE}>
              <thead><tr>
                <th style={TH}>Entity</th><th style={TH}>Link Type</th><th style={TH}>From Part</th>
              </tr></thead>
              <tbody>
                {data.realization_chain.map((r, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? C.surface : C.bg }}>
                    <td style={TD}><span style={{ fontWeight: 700, color: C.primaryText }}>{businessDisplayName(r.name)}</span></td>
                    <td style={TD}><Badge color={C.orange}>{r.link_type || 'Ã¢â‚¬â€'}</Badge></td>
                    <td style={TD}><span style={{ color: C.primaryText, fontWeight: 600 }}>{r.from_part || 'Ã¢â‚¬â€'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No realization chain found.</div>
      )}
      </ResultTabBar>
    </div>
  );
};

export { ChangeImpactResult };
