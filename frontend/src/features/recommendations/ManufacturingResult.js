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
  const tabs = [
    { id: 'overview',  label: 'Overview',           color: C.green  },
    { id: 'direct',    label: 'Direct Processes',    color: C.primaryText, count: data.direct_processes?.length          || 0 },
    { id: 'instances', label: 'Process Instances',   color: C.orange,  count: data.process_instances?.length         || 0 },
    { id: 'related',   label: 'Related Processes',   color: C.amber,   count: data.related_part_processes?.length    || 0 },
    { id: 'summary',   label: 'Type Summary',        color: C.primaryText  },
  ];

  return (
    <div>
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
              <div style={{ fontSize: '22px', fontWeight: 700, color: C.orange }}>{summary.total_instances || 0}</div>
              <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase' }}>Instances</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: '22px', fontWeight: 700, color: C.amber }}>{summary.total_related || 0}</div>
              <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase' }}>Related</div>
            </div>
          </div>
        </div>
      </div>

      <ResultTabBar tabs={tabs} active={tab} onChange={setTab} />

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
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No process instances.</div>
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
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No related processes.</div>
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
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No type summary.</div>
      )}
    </div>
  );
};

export { ManufacturingResult };
