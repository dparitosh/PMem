import { ProcessFlowTimeline } from "./RecommendationVisuals.js";
import { CARD, TH, TD, TABLE, Badge, ResultTabBar } from "./RecommendationPrimitives.js";
import React, { useState } from "react";
import { Factory } from "lucide-react";
import { UI_COLORS as C } from "../../styles/uiTokens";

const ManufacturingResult = ({ data }) => {
  const [tab, setTab] = useState('overview');
  if (data.message && !data.part) {
    return <div style={CARD}><em style={{ color: C.textSec }}>{data.message}</em></div>;
  }

  const pt = data.part || {};
  const summary = data.process_summary || {};
  const instancesAssessed = data.assessment?.process_instances === 'assessed' || data.process_instances?.length > 0;
  const relatedAssessed = data.assessment?.related_processes === 'assessed' || data.related_part_processes?.length > 0;
  const tabs = [
    { id: 'overview',  label: 'Overview',           color: C.green  },
    { id: 'direct',    label: 'Direct Processes',    color: C.primaryText, count: data.direct_processes?.length          || 0 },
    { id: 'instances', label: 'Process Instances',   color: C.orange,  count: instancesAssessed ? data.process_instances?.length || 0 : undefined },
    { id: 'related',   label: 'Related Processes',   color: C.amber,   count: relatedAssessed ? data.related_part_processes?.length || 0 : undefined },
    { id: 'summary',   label: 'Type Summary',        color: C.primaryText  },
  ];

  return (
    <div>
      {data.coverage?.limit_reached&&<p role="status">The neighbor limit was reached. These process results cover only the inspected graph slice; narrow the scope to investigate further.</p>}
      {data.message&&<p role="status">{data.message}</p>}
      {/* Header Ã¢â‚¬â€ always visible */}
      <div style={CARD}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '14px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <Factory size={17} color={C.green} strokeWidth={2.5} />
              <span style={{ fontSize: '15px', fontWeight: 700, color: C.textPrimary }}>
                Processes for: <span style={{ color: C.green }}>{pt.name}</span>
              </span>
            </div>
            <Badge color={C.green}>{pt.source_tag}</Badge>
          </div>
          <div style={{ display: 'flex', gap: '20px' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '22px', fontWeight: 700, color: C.primaryText }}>{summary.total_direct || 0}</div>
              <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase' }}>Direct</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '22px', fontWeight: 700, color: C.orange }}>{instancesAssessed ? summary.total_instances ?? data.process_instances?.length ?? 0 : 'Not assessed'}</div>
              <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase' }}>Instances</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '22px', fontWeight: 700, color: C.amber }}>{relatedAssessed ? summary.total_related ?? data.related_part_processes?.length ?? 0 : 'Not assessed'}</div>
              <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase' }}>Related</div>
            </div>
          </div>
        </div>
      </div>

      <ResultTabBar tabs={tabs} active={tab} onChange={setTab}>

      {tab === 'overview' && <ProcessFlowTimeline data={data} />}

      {tab === 'direct' && (
        data.direct_processes?.length > 0 ? (
          <div style={CARD}>
            <table style={TABLE}>
              <thead><tr>
                <th style={TH}>Process</th><th style={TH}>Type</th><th style={TH}>File</th>
              </tr></thead>
              <tbody>
                {data.direct_processes.map((p, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? C.surface : C.bg }}>
                    <td style={TD}><span style={{ fontWeight: 700, color: C.green }}>{p.process_name}</span></td>
                    <td style={TD}><Badge color={C.green}>{p.source_tag || 'Ã¢â‚¬â€'}</Badge></td>
                    <td style={TD}><span style={{ color: C.textSec, fontSize: '12px' }}>{p.file_name || 'Ã¢â‚¬â€'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No direct processes.</div>
      )}

      {tab === 'instances' && (
        data.process_instances?.length > 0 ? (
          <div style={CARD}>
            <table style={TABLE}>
              <thead><tr>
                <th style={TH}>Instance</th><th style={TH}>Type</th><th style={TH}>References</th>
              </tr></thead>
              <tbody>
                {data.process_instances.map((p, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? C.surface : C.bg }}>
                    <td style={TD}><span style={{ fontWeight: 700, color: C.orange }}>{p.name}</span></td>
                    <td style={TD}><Badge color={C.orange}>{p.source_tag || 'Ã¢â‚¬â€'}</Badge></td>
                    <td style={TD}><span style={{ color: C.primaryText, fontWeight: 600 }}>{p.references_instance || 'Ã¢â‚¬â€'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>{instancesAssessed ? 'No process instances found in the assessed scope.' : 'Process instances are not assessed by this analysis. Direct processes cover recorded neighbors only.'}</div>
      )}

      {tab === 'related' && (
        data.related_part_processes?.length > 0 ? (
          <div style={CARD}>
            <table style={TABLE}>
              <thead><tr>
                <th style={TH}>Process</th><th style={TH}>For Part</th><th style={TH}>Relation</th>
              </tr></thead>
              <tbody>
                {data.related_part_processes.map((p, i) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? C.surface : C.bg }}>
                    <td style={TD}><span style={{ fontWeight: 700, color: C.amber }}>{p.process_name}</span></td>
                    <td style={TD}><span style={{ color: C.primaryText, fontWeight: 600 }}>{p.part_name || 'Ã¢â‚¬â€'}</span></td>
                    <td style={TD}><Badge color={C.amber}>{p.relation || 'Ã¢â‚¬â€'}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>{relatedAssessed ? 'No related processes found in the assessed scope.' : 'Related processes are not assessed by this analysis. Direct processes cover recorded neighbors only.'}</div>
      )}

      {tab === 'summary' && (
        summary.by_type && Object.keys(summary.by_type).length > 0 ? (
          <div style={CARD}>
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              {Object.entries(summary.by_type).map(([type, procs]) => (
                <div key={type} style={{
                  padding: '12px 18px', borderRadius: '8px',
                  background: C.primaryLight, border: `1px solid ${C.primary}20`, minWidth: '130px',
                }}>
                  <div style={{ fontSize: '13px', fontWeight: 700, color: C.primaryText }}>{type}</div>
                  <div style={{ fontSize: '22px', fontWeight: 700, color: C.textPrimary, margin: '4px 0' }}>{procs.length}</div>
                  <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase' }}>processes</div>
                </div>
              ))}
            </div>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>Process type summary is not assessed by this analysis.</div>
      )}
      </ResultTabBar>
    </div>
  );
};

export { ManufacturingResult };
