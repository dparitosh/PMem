import React from 'react';
import { UI_COLORS as C } from '../../styles/uiTokens';

const INFERENCE_RULES = [
  ['transitive_subclass', 'Transitive subclass hierarchy', 'Find indirect superclass paths for taxonomy and classification.'],
  ['domain_range_typing', 'Domain/range typing', 'Use property domain and range to explain expected source and target classes.'],
  ['equivalence', 'Equivalent terms', 'Preview same-as, equivalent class/property, and exact-match mappings.'],
  ['disjointness', 'Disjointness checks', 'Surface disjoint classes that should not classify the same individual.'],
  ['individual_type_closure', 'Individual type closure', 'Infer broader individual types from declared class hierarchy.'],
];

export default function OntologyInferenceWorkbench(props) {
  const {
    selectedOntologyApi,
    inferenceBusy,
    runInferencePreview,
    inferenceRules,
    toggleInferenceRule,
    swrlExpression,
    setSwrlExpression,
    swrlValidation,
    swrlBusy,
    validateSwrlExpression,
    inferenceLimit,
    setInferenceLimit,
    inferenceError,
    inferenceResult,
    reasoning,
    filter,
  } = props;

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: '8px', padding: '14px', minHeight: '360px' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <div>
          <div style={{ fontSize: '14px', fontWeight: 800, color: C.textPrimary }}>Ontology inference preview</div>
          <div style={{ fontSize: '12px', color: C.textSec, marginTop: '3px' }}>Choose reasoning patterns, preview inferred statements, then decide what belongs in Semantic Bridge or graph materialization.</div>
        </div>
        <button
          type="button"
          onClick={runInferencePreview}
          disabled={inferenceBusy || !selectedOntologyApi}
          style={{ padding: '8px 14px', borderRadius: '6px', border: 'none', background: inferenceBusy || !selectedOntologyApi ? C.textMuted : C.primary, color: '#fff', fontSize: '12px', fontWeight: 800, cursor: inferenceBusy || !selectedOntologyApi ? 'not-allowed' : 'pointer' }}
        >
          {inferenceBusy ? 'Previewing' : 'Run preview'}
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(260px, 360px) 1fr', gap: '12px', alignItems: 'start' }}>
        <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', padding: '12px', background: C.bg }}>
          <div style={{ fontSize: '11px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '8px' }}>Inference rules</div>
          {INFERENCE_RULES.map(([id, label, help]) => (
            <label key={id} style={{ display: 'grid', gridTemplateColumns: '18px 1fr', gap: '8px', padding: '8px 0', borderBottom: `1px solid ${C.border}` }}>
              <input type="checkbox" checked={Boolean(inferenceRules[id])} onChange={() => toggleInferenceRule(id)} />
              <span>
                <span style={{ display: 'block', fontSize: '12px', fontWeight: 800, color: C.textPrimary }}>{label}</span>
                <span style={{ display: 'block', fontSize: '11px', color: C.textSec, lineHeight: 1.4 }}>{help}</span>
              </span>
            </label>
          ))}
          <div style={{ marginTop: '12px', paddingTop: '10px', borderTop: `1px solid ${C.border}` }}>
            <div style={{ fontSize: '11px', fontWeight: 800, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '6px' }}>SWRL-style rule editor</div>
            <textarea
              value={swrlExpression}
              onChange={(e) => setSwrlExpression(e.target.value)}
              rows={4}
              spellCheck={false}
              style={{ width: '100%', boxSizing: 'border-box', padding: '8px 9px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', fontSize: '11px', lineHeight: 1.45, fontFamily: 'monospace', resize: 'vertical' }}
            />
            <button
              type="button"
              onClick={validateSwrlExpression}
              disabled={swrlBusy || !swrlExpression.trim()}
              style={{ marginTop: '8px', padding: '7px 10px', borderRadius: '6px', border: 'none', background: swrlBusy || !swrlExpression.trim() ? C.textMuted : C.primary, color: '#fff', fontSize: '11px', fontWeight: 800, cursor: swrlBusy || !swrlExpression.trim() ? 'not-allowed' : 'pointer' }}
            >
              {swrlBusy ? 'Validating' : 'Validate rule'}
            </button>
            {swrlValidation && (
              <div style={{ marginTop: '8px', border: `1px solid ${swrlValidation.valid ? C.green : C.red}`, background: swrlValidation.valid ? '#F0FFF4' : '#FFF5F5', color: swrlValidation.valid ? C.green : C.red, borderRadius: '6px', padding: '8px', fontSize: '11px', lineHeight: 1.4 }}>
                <div style={{ fontWeight: 800 }}>{swrlValidation.valid ? 'Rule supported' : 'Rule needs correction'}</div>
                <div style={{ color: C.textPrimary, marginTop: '4px' }}>{swrlValidation.preview}</div>
                {(swrlValidation.issues || []).slice(0, 4).map((issue, idx) => (
                  <div key={`${issue.code}-${idx}`} style={{ marginTop: '4px' }}>{issue.code}: {issue.message}</div>
                ))}
              </div>
            )}
          </div>
          <label style={{ display: 'block', marginTop: '10px', fontSize: '11px', fontWeight: 800, color: C.textSec }}>Preview limit</label>
          <input
            type="number"
            min="25"
            max="1000"
            value={inferenceLimit}
            onChange={(e) => setInferenceLimit(e.target.value)}
            style={{ width: '100%', marginTop: '5px', padding: '7px 9px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', fontSize: '12px' }}
          />
        </div>
        <div style={{ minWidth: 0 }}>
          {inferenceError && (
            <div style={{ marginBottom: '10px', padding: '8px 10px', borderRadius: '6px', border: `1px solid ${C.red}`, background: '#FFF5F5', color: C.red, fontSize: '12px', fontWeight: 700 }}>{inferenceError}</div>
          )}
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '10px' }}>
            {[
              ['Candidates', inferenceResult?.summary?.inferred_candidates ?? 0],
              ['Classes', inferenceResult?.summary?.classes ?? reasoning?.summary?.classes ?? 0],
              ['Properties', (inferenceResult?.summary?.object_properties ?? reasoning?.summary?.object_properties ?? 0) + (inferenceResult?.summary?.datatype_properties ?? reasoning?.summary?.datatype_properties ?? 0)],
              ['Individuals', inferenceResult?.summary?.individuals ?? reasoning?.summary?.individuals ?? 0],
            ].map(([label, value]) => (
              <div key={label} style={{ padding: '6px 10px', borderRadius: '999px', border: `1px solid ${C.border}`, background: C.bg, fontSize: '11px', fontWeight: 800, color: C.textPrimary }}>{label}: {value}</div>
            ))}
          </div>
          {(inferenceResult?.warnings || []).map((warning, idx) => (
            <div key={idx} style={{ marginBottom: '8px', padding: '8px 10px', borderRadius: '6px', border: '1px solid #F7C948', background: '#FFF8E1', color: '#8A5A00', fontSize: '12px', fontWeight: 700 }}>{warning}</div>
          ))}
          <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'hidden', background: C.surface }}>
            <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr 130px 1fr 90px', gap: 0, background: C.primary, color: '#fff', fontSize: '11px', fontWeight: 800 }}>
              {['Rule', 'Subject', 'Predicate', 'Object', 'Confidence'].map((header) => <div key={header} style={{ padding: '9px 10px' }}>{header}</div>)}
            </div>
            {(inferenceResult?.inferences || [])
              .filter((row) => {
                const q = String(filter || '').toLowerCase();
                if (!q) return true;
                return [row.rule, row.subject_label, row.predicate, row.object_label, row.evidence].some((value) => String(value || '').toLowerCase().includes(q));
              })
              .slice(0, Number(inferenceLimit) || 250)
              .map((row, idx) => (
                <div key={`${row.rule}-${row.subject}-${row.object}-${idx}`} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 130px 1fr 90px', borderTop: `1px solid ${C.border}`, fontSize: '12px', color: C.textPrimary }}>
                  <div style={{ padding: '9px 10px', fontWeight: 800 }}>{String(row.rule || '').replaceAll('_', ' ')}</div>
                  <div style={{ padding: '9px 10px', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }} title={row.subject}>{row.subject_label || row.subject}</div>
                  <div style={{ padding: '9px 10px', color: C.textSec, fontWeight: 700 }}>{row.predicate}</div>
                  <div style={{ padding: '9px 10px', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }} title={row.object}>{row.object_label || row.object}</div>
                  <div style={{ padding: '9px 10px', fontWeight: 800 }}>{Math.round((Number(row.confidence) || 0) * 100)}%</div>
                  {row.evidence && <div style={{ gridColumn: '1 / -1', padding: '0 10px 9px 10px', color: C.textSec, fontSize: '11px' }}>{row.evidence}</div>}
                </div>
              ))}
            {!inferenceResult && (
              <div style={{ padding: '28px', textAlign: 'center', color: C.textSec, fontSize: '13px' }}>Run preview to inspect inferred ontology statements.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
