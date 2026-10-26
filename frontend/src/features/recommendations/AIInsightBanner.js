import { MetricChip } from "./RecommendationPrimitives.js";
import React from "react";
import { Info } from "lucide-react";
import { UI_COLORS as C } from "../../styles/uiTokens";

const AIInsightBanner = ({ service, data }) => {
  let insight = null;

  if (service === 'change-impact' && data?.change_entity) {
    const partCount = data.impacted_parts?.length || 0;
    const asmCount  = data.assembly_impact?.length || 0;
    const procCount = data.process_impacts?.length || 0;
    const reqCount  = data.impacted_requirements?.length || 0;
    const color = C.primaryText;
    const bg = C.primaryLight;
    const Icon = Info;
    const headline = data.evidence_status === 'insufficient' ? 'Impact is not established' : 'Linked impact candidates for review';
    insight = {
      color, bg, Icon, headline,
      chips: [
        { value: partCount, label: 'Parts' },
        { value: asmCount,  label: 'Assemblies' },
        { value: reqCount,  label: 'Requirements' },
        { value: procCount, label: 'Processes' },
      ],
      cta: 'Direct links support investigation. Impact severity and indirect effects have not been assessed.',
    };
  } else if (service === 'similar-parts' && data?.source_part) {
    const count = data.similar_parts?.length || 0;
    insight = {
      color: C.primaryText, bg: C.primaryLight, Icon: Info,
      headline: `${count} candidate part${count !== 1 ? 's' : ''} identified for reuse consideration`,
      chips: [{ value: count, label: 'Candidates' }],
      cta: data.ranking_scope || 'Review candidate score evidence before deciding whether a part can be reused. Similarity is not a probability or an approval.',
    };
  } else if (service === 'manufacturing' && data?.part) {
    const direct = data.process_summary?.total_direct    || 0;
    const inst   = data.process_summary?.total_instances || 0;
    const rel    = data.process_summary?.total_related   || 0;
    insight = {
      color: C.green, bg: C.greenLight, Icon: Info,
      headline: `Process landscape mapped Ã¢â‚¬â€ ${direct + inst + rel} total process${(direct + inst + rel) !== 1 ? 'es' : ''} identified`,
      chips: [
        { value: direct, label: 'Direct' },
        { value: inst,   label: 'Instances' },
        { value: rel,    label: 'Related' },
      ],
      cta: 'Confirm the sequence against the manufacturing plan.',
    };
  }

  if (!insight) {
    insight = {
      color: C.primaryText,
      bg: C.primaryLight,
      Icon: Info,
      headline: 'No structured recommendation evidence',
      chips: [],
      cta: data?.message || 'The recommendation service returned a response, but there is no structured summary for this result yet.',
    };
  }
  const { color, bg, Icon, headline, chips, cta } = insight;
  return (
    <div style={{
      background: bg,
      borderRadius: '10px',
      borderLeft: `5px solid ${color}`,
      border: `1px solid color-mix(in srgb, ${color} 20%, transparent)`,
      padding: '16px 20px 18px',
      marginBottom: '14px',
      width: '100%',
      boxSizing: 'border-box',
    }}>
      {/* Headline row Ã¢â‚¬â€ inline layout avoids flex shrink bug */}
      <div style={{ marginBottom: '14px', lineHeight: 1.5 }}>
        <Icon
          size={15}
          color={color}
          strokeWidth={2.5}
          style={{ display: 'inline', verticalAlign: 'middle', marginRight: '7px', flexShrink: 0 }}
        />
        <span style={{ fontSize: '13px', fontWeight: 700, color, verticalAlign: 'middle' }}>{headline}</span>
      </div>

      {/* Metric chips */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginBottom: '14px' }}>
        {chips.map(({ value, label }) => (
          <MetricChip key={label} value={value} label={label} color={color} />
        ))}
      </div>

      {/* CTA line */}
      <div style={{
        fontSize: '13px', color: C.textPrimary, lineHeight: 1.7,
        paddingTop: '12px', borderTop: `1px solid color-mix(in srgb, ${color} 20%, transparent)`,
      }}>
        {cta}
      </div>
    </div>
  );
};

export { AIInsightBanner };
