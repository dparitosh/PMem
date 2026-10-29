import React, { useState } from 'react';
import ReadGoalPanel from '../ReadGoalPanel';
import OntologyFoundationPanel from './OntologyFoundationPanel';
import { UI_COLORS as C } from '../../styles/uiTokens';

const INFERENCE_RULES = [
  ['inverse_properties', 'Inverse properties', 'Preview reverse instance links from declared inverse properties.'],
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

  const [question, setQuestion] = useState('Explain the inferred statements, supporting declarations, disjointness findings and limitations for this ontology.');
  const investigationKey = JSON.stringify([selectedOntologyApi, inferenceRules, inferenceLimit]);

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.border}`, borderRadius: '8px', padding: '14px', minHeight: '360px' }}>
      <OntologyFoundationPanel ontologyId={selectedOntologyApi} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <div>
          <div style={{ fontSize: '14px', fontWeight: 800, color: C.textPrimary }}>Ontology inference preview</div>
          <div style={{ fontSize: '12px', color: C.textSec, marginTop: '3px' }}>Choose structural rules and inspect their conclusions and supporting declarations. This workbench does not apply or publish them.</div>
        </div>
        <button
          type="button"
          onClick={runInferencePreview}
          disabled={inferenceBusy || !selectedOntologyApi || !Object.values(inferenceRules || {}).some(Boolean)}
          style={{ padding: '8px 14px', borderRadius: '6px', border: 'none', background: inferenceBusy || !selectedOntologyApi ? C.textMuted : C.primary, color: '#fff', fontSize: '12px', fontWeight: 800, cursor: inferenceBusy || !selectedOntologyApi ? 'not-allowed' : 'pointer' }}
        >
          {inferenceBusy ? 'Previewing' : 'Run preview'}
        </button>
      </div>

      <section aria-label="Inference agent" style={{ padding: 12, marginBottom: 12, border: `1px solid ${C.border}`, borderRadius: 8 }}>
        <h3>Ontology Inference Advisor</h3>
        <p>Ask the agent to plan an investigation, run the selected inference rules and explain evidence using ontology IRIs. The model-assisted explanation remains separate from the structural rule preview.</p>
        <label htmlFor="inference-agent-question">What would you like to understand?</label>
        <textarea id="inference-agent-question" value={question} onChange={event => setQuestion(event.target.value)} maxLength={8000} rows={2} style={{ display: 'block', width: '100%', boxSizing: 'border-box' }} />
        {selectedOntologyApi ? <ReadGoalPanel key={investigationKey} storageKey={`depo:inference-goal:${investigationKey}`} agent="ontology-inference" task={question}
          context={{ ontology_id: selectedOntologyApi, rules: inferenceRules, limit: Number(inferenceLimit) }} />
          : <p>Select an active ontology to investigate its inferences.</p>}
        <p>Requires a configured OpenAI, Mistral or Ollama model and the agent worker. Plans, tool evidence and conclusions are retained; no graph changes are made.</p>
      </section>

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
            <p>Validation checks the supported rule syntax only. This expression is not executed by Run preview.</p>
            <textarea
              aria-label="SWRL-style rule expression"
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
              <div style={{ marginTop: '8px', border: `1px solid ${swrlValidation.valid ? C.green : C.red}`, background: swrlValidation.valid ? 'var(--ui-surface)'  : 'var(--ui-surface)' , color: swrlValidation.valid ? C.green : C.red, borderRadius: '6px', padding: '8px', fontSize: '11px', lineHeight: 1.4 }}>
                <div style={{ fontWeight: 800 }}>{swrlValidation.valid ? 'Supported syntax — not executed' : 'Rule needs correction'}</div>
                <div style={{ color: C.textPrimary, marginTop: '4px' }}>{swrlValidation.preview}</div>
                {(swrlValidation.issues || []).slice(0, 4).map((issue, idx) => (
                  <div key={`${issue.code}-${idx}`} style={{ marginTop: '4px' }}>{issue.code}: {issue.message}</div>
                ))}
              </div>
            )}
          </div>
          <label style={{ display: 'block', marginTop: '10px', fontSize: '11px', fontWeight: 800, color: C.textSec }}>Preview limit</label>
          <input
            aria-label="Inference preview limit"
            type="number"
            min="25"
            max="1000"
            value={inferenceLimit}
            onChange={(e) => setInferenceLimit(e.target.value)}
            style={{ width: '100%', marginTop: '5px', padding: '7px 9px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', fontSize: '12px' }}
          />
        </div>
        <div style={{ minWidth: 0 }}>
          <p>Structural rule candidates are review evidence, not a full logical consistency proof. This preview does not publish changes.</p>
          {inferenceError && (
            <div style={{ marginBottom: '10px', padding: '8px 10px', borderRadius: '6px', border: `1px solid ${C.red}`, background: 'var(--ui-surface)' , color: C.red, fontSize: '12px', fontWeight: 700 }}>{inferenceError}</div>
          )}
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '10px' }}>
            {[
              ['Candidates', inferenceResult?.summary?.inferred_candidates ?? 'Not run'],
              ['Classes', inferenceResult?.summary?.classes ?? reasoning?.summary?.classes ?? 'Unavailable'],
              ['Properties', (inferenceResult?.summary || reasoning?.summary) ? ((inferenceResult?.summary?.object_properties ?? reasoning?.summary?.object_properties ?? 0) + (inferenceResult?.summary?.datatype_properties ?? reasoning?.summary?.datatype_properties ?? 0)) : 'Unavailable'],
              ['Individuals', inferenceResult?.summary?.individuals ?? reasoning?.summary?.individuals ?? 'Unavailable'],
            ].map(([label, value]) => (
              <div key={label} style={{ padding: '6px 10px', borderRadius: '999px', border: `1px solid ${C.border}`, background: C.bg, fontSize: '11px', fontWeight: 800, color: C.textPrimary }}>{label}: {value}</div>
            ))}
          </div>
          {(inferenceResult?.warnings || []).map((warning, idx) => (
            <div key={idx} style={{ marginBottom: '8px', padding: '8px 10px', borderRadius: '6px', border: '1px solid #F7C948', background: 'var(--ui-surface)' , color: 'var(--ui-text)' , fontSize: '12px', fontWeight: 700 }}>{warning}</div>
          ))}
          <div style={{ border: `1px solid ${C.border}`, borderRadius: '8px', overflow: 'hidden', background: C.surface }}>
            <div style={{ display: 'grid', gridTemplateColumns: '150px 1fr 130px 1fr 90px', gap: 0, background: C.primary, color: '#fff', fontSize: '11px', fontWeight: 800 }}>
              {['Rule', 'Subject', 'Predicate', 'Object', 'Support'].map((header) => <div key={header} style={{ padding: '9px 10px' }}>{header}</div>)}
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
                  <div style={{ padding: '9px 10px', fontWeight: 800 }}>{row.support || 'Rule candidate'}</div>
                  {row.evidence && <div style={{ gridColumn: '1 / -1', padding: '0 10px 9px 10px', color: C.textSec, fontSize: '11px' }}>{row.evidence}</div>}
                </div>
              ))}
            {!inferenceResult && (
              <div style={{ padding: '28px', textAlign: 'center', color: C.textSec, fontSize: '13px' }}>Run preview to inspect inferred ontology statements.</div>
            )}
            {inferenceResult && !inferenceResult.inferences?.length && <p>No statement candidates were returned. Review domain/range declarations below if that rule is selected.</p>}
          </div>
          {inferenceResult?.constraints?.length > 0 && <section aria-label="Domain and range declarations"><h4>Domain and range declarations</h4><p>These are property declarations, not inferred instance types.</p><div style={{overflowX:'auto'}}><table><thead><tr><th>Property</th><th>Declaration</th><th>Class or datatype</th></tr></thead><tbody>{inferenceResult.constraints.map((row,index) => <tr key={index}><td title={row.property}>{row.property_label || row.property}</td><td>{row.kind}</td><td>{row.class}</td></tr>)}</tbody></table></div></section>}
          {inferenceResult?.summary?.truncated && <p role="status">The preview is incomplete at the selected limit. Increase the limit or narrow the ontology.</p>}
        </div>
      </div>
    </div>
  );
}
