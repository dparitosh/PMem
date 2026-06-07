import React, { useState, useCallback, useEffect, useRef } from 'react';
import * as d3 from 'd3';
import {
  Zap, Search, Factory, Eye,
  BarChart2, Target,
  CheckCircle, Minus, AlertTriangle,
  Info,
} from 'lucide-react';
import { API_METHODS } from '../services/apiClient';

// ============================================================
// Corporate Design Tokens — TCS Blue / Infineon Brand System
// ============================================================
const C = {
  primary:      '#004B87',
  primaryDark:  '#003366',
  primaryLight: '#E8F1FC',
  primaryHover: '#0066CC',
  orange:       '#FF6900',
  orangeLight:  '#FFF5F0',
  green:        '#28A745',
  greenLight:   '#F0FFF4',
  amber:        '#E6A817',
  amberLight:   '#FFFBEB',
  red:          '#C0392B',
  redLight:     '#FEF2F2',
  textPrimary:  '#1A2B3C',
  textSec:      '#6C757D',
  textMuted:    '#ADB5BD',
  border:       '#E9ECEF',
  borderDark:   '#CED4DA',
  bg:           '#F8F9FA',
  surface:      '#FFFFFF',
};

// ————— Layout primitives ——————————————————————————————
const CARD = {
  background: C.surface,
  borderRadius: '10px',
  border: `1px solid ${C.border}`,
  boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
  padding: '20px 24px',
  marginBottom: '14px',
  width: '100%',
  boxSizing: 'border-box',
  minWidth: 0,
};

const TH = {
  textAlign: 'left',
  padding: '9px 12px',
  borderBottom: `2px solid ${C.primary}`,
  color: C.primary,
  fontWeight: 700,
  fontSize: '11px',
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
};

const TD = {
  padding: '8px 12px',
  borderBottom: `1px solid ${C.border}`,
  verticalAlign: 'top',
  fontSize: '13px',
  color: C.textPrimary,
};

const TABLE = { width: '100%', borderCollapse: 'collapse', fontSize: '13px' };

// ————— Shared UI components ———————————————————————————
const Badge = ({ color = C.primary, children }) => (
  <span style={{
    display: 'inline-block', padding: '2px 9px', borderRadius: '10px',
    fontSize: '11px', fontWeight: 600, background: color, color: '#fff',
    marginRight: '5px',
  }}>{children}</span>
);

const ScoreBar = ({ score, max = 100 }) => {
  const pct = Math.min((score / max) * 100, 100);
  const barColor = score > 70 ? C.red : score > 40 ? C.amber : C.green;
  const label = score > 70 ? 'High Impact' : score > 40 ? 'Medium Impact' : 'Low Impact';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
      <div style={{ flex: 1, height: '8px', background: C.border, borderRadius: '4px', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: barColor, borderRadius: '4px', transition: 'width .4s ease' }} />
      </div>
      <span style={{ fontSize: '12px', fontWeight: 700, color: barColor, minWidth: '100px', whiteSpace: 'nowrap' }}>
        {score} — {label}
      </span>
    </div>
  );
};

const SimilarityBar = ({ score }) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
    <div style={{ width: '80px', height: '6px', background: C.border, borderRadius: '3px', overflow: 'hidden' }}>
      <div style={{ width: `${Math.min(score, 100)}%`, height: '100%', background: C.primary, borderRadius: '3px' }} />
    </div>
    <span style={{ fontSize: '12px', fontWeight: 600, color: C.textSec }}>{score}</span>
  </div>
);

// ————— Icon + label section header —————————————————————
const SectionHeader = ({ icon: Icon, label, count, color = C.primary }) => (
  <div style={{
    fontSize: '12px', fontWeight: 700, color: C.textPrimary, marginBottom: '12px',
    marginTop: '20px', display: 'flex', alignItems: 'center', gap: '8px',
    textTransform: 'uppercase', letterSpacing: '0.05em',
  }}>
    <Icon size={14} color={color} strokeWidth={2.5} />
    <span>{label}</span>
    {count !== undefined && (
      <span style={{
        background: C.primaryLight, color: C.primary,
        fontSize: '11px', fontWeight: 700, padding: '1px 8px', borderRadius: '10px',
      }}>{count}</span>
    )}
  </div>
);

// Check / blank cell indicator
const CheckCell = ({ value }) => value
  ? <CheckCircle size={14} color={C.green} strokeWidth={2.5} />
  : <Minus size={13} color={C.textMuted} />;

// ============================================================
// Helper: "View in Graph" — dispatches highlight event and switches tab
// ============================================================
const viewInGraph = (nodeNames, setActiveTab) => {
  const names = Array.isArray(nodeNames) ? nodeNames : [nodeNames];

  // Store pending values so GraphHEB can pick them up in case it processes
  // the events before its useEffect listeners have run
  window.__dt_pending_highlight = names;
  window.__dt_pending_result_nodes = names;

  // GraphHEB is always mounted above the tab panels — dispatch immediately.
  // dt-load-result-nodes fetches the exact named nodes from Neo4j and
  // replaces the current graph content with those result nodes.
  window.dispatchEvent(new CustomEvent('dt-load-result-nodes', { detail: { names } }));
  // dt-highlight-nodes marks each result node with a gold ring once loaded
  window.dispatchEvent(new CustomEvent('dt-highlight-nodes', { detail: { names } }));

  if (typeof setActiveTab === 'function') setActiveTab('graph');
  window.scrollTo({ top: 0, behavior: 'smooth' });
};

// ============================================================
// Result sub-tab bar — reused across all three result components
// ============================================================
const ResultTabBar = ({ tabs, active, onChange }) => (
  <div style={{
    display: 'flex', gap: 0, borderBottom: `1px solid ${C.border}`,
    background: C.surface, marginBottom: '14px', flexWrap: 'wrap',
    borderRadius: '8px 8px 0 0', padding: '0 4px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
  }}>
    {tabs.map(t => {
      const isActive = active === t.id;
      const col = t.color || C.primary;
      return (
        <button key={t.id} onClick={() => onChange(t.id)} style={{
          display: 'inline-flex', alignItems: 'center', gap: '5px',
          padding: '9px 14px', border: 'none', background: 'transparent',
          borderBottom: isActive ? `2px solid ${col}` : '2px solid transparent',
          color: isActive ? col : C.textSec,
          fontSize: '12px', fontWeight: isActive ? 700 : 500,
          cursor: 'pointer', transition: 'all .12s', marginBottom: '-1px',
          whiteSpace: 'nowrap',
        }}>
          {t.label}
          {t.count !== undefined && (
            <span style={{
              background: isActive ? col : C.border,
              color: isActive ? '#fff' : C.textSec,
              fontSize: '10px', fontWeight: 700,
              padding: '1px 6px', borderRadius: '10px', minWidth: '18px', textAlign: 'center',
            }}>{t.count}</span>
          )}
        </button>
      );
    })}
  </div>
);

const ViewGraphBtn = ({ names, setActiveTab }) => (
  <button
    onClick={() => viewInGraph(names, setActiveTab)}
    onMouseEnter={e => { e.currentTarget.style.background = C.primary; e.currentTarget.style.color = '#fff'; }}
    onMouseLeave={e => { e.currentTarget.style.background = C.primaryLight; e.currentTarget.style.color = C.primary; }}
    style={{
      display: 'inline-flex', alignItems: 'center', gap: '6px',
      padding: '7px 16px', border: `1px solid ${C.primary}`, borderRadius: '6px',
      background: C.primaryLight, color: C.primary, fontSize: '13px', fontWeight: 600,
      cursor: 'pointer', marginTop: '12px', transition: 'all .18s ease',
    }}
  >
    <Eye size={14} strokeWidth={2.5} />
    View in Graph ({names.length} nodes)
  </button>
);

// ============================================================
// Welcome / Scenario Panel — shown when no service is selected
// ============================================================
const ScenarioPanel = ({ onSelect }) => {
  const scenarios = [
    {
      id: 'change-impact',
      Icon: Zap,
      color: C.orange,
      lightColor: C.orangeLight,
      title: 'Change Impact Analysis',
      tagline: 'Understand downstream consequences before approving a change.',
      scenario: `A design engineer raised a change request to modify the bearing-shaft fit tolerance on the Induction Motor Assembly. Before the Change Control Board approves it, they need to know: which parts, assemblies, requirements, and production processes will be affected downstream?`,
      tryWith: 'Change the fit between bearing and shaft',
      tryLabel: 'Try this example',
    },
    {
      id: 'similar-parts',
      Icon: Search,
      color: C.primary,
      lightColor: C.primaryLight,
      title: 'Similar Parts Discovery',
      tagline: 'Identify reusable parts to reduce procurement cost and design duplication.',
      scenario: `A procurement lead is evaluating whether to source a new Rotor Shaft variant or reuse an existing part from another product line. The AI surfaces structurally and semantically similar parts by comparing assembly co-occurrence, type, RFLP layer, and traceability links — you review and decide.`,
      tryWith: 'Rotor Shaft Machined',
      tryLabel: 'Try this example',
    },
    {
      id: 'manufacturing',
      Icon: Factory,
      color: C.green,
      lightColor: C.greenLight,
      title: 'Manufacturing Process',
      tagline: 'Discover which processes apply to a part across the full production chain.',
      scenario: `A process planner needs to document all manufacturing steps for the Motor Cover before submitting the production order. Instead of manually cross-referencing PLM files, the AI traverses direct process links, process instance chains, and related assembly processes to deliver a complete process picture for human review.`,
      tryWith: 'Motor Cover Machined',
      tryLabel: 'Try this example',
    },
  ];

  return (
    <div>
      <div style={{
        background: `linear-gradient(135deg, ${C.primary} 0%, ${C.primaryDark} 100%)`,
        borderRadius: '10px', padding: '22px 28px', marginBottom: '20px', color: '#fff',
      }}>
        <div style={{ fontSize: '18px', fontWeight: 700, marginBottom: '6px', letterSpacing: '-0.01em' }}>
          AI Recommendation Engine
        </div>
        <div style={{ fontSize: '13px', opacity: 0.85, maxWidth: '600px', lineHeight: 1.65 }}>
          Select an analysis mode below. The AI traverses the knowledge graph on your behalf — you review the findings and decide the next action. Each service is designed to keep <strong>you</strong> in control of the decision.
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {scenarios.map(s => (
          <div
            key={s.id}
            onClick={() => onSelect(s.id)}
            onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.1)'; e.currentTarget.style.transform = 'translateY(-1px)'; }}
            onMouseLeave={e => { e.currentTarget.style.boxShadow = '0 1px 4px rgba(0,0,0,0.06)'; e.currentTarget.style.transform = 'none'; }}
            style={{
              ...CARD, marginBottom: 0, cursor: 'pointer',
              borderLeft: `4px solid ${s.color}`,
              display: 'flex', gap: '16px', alignItems: 'flex-start',
              transition: 'box-shadow .18s ease, transform .18s ease',
            }}
          >
            <div style={{
              flexShrink: 0, width: '42px', height: '42px', borderRadius: '10px',
              background: s.lightColor, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <s.Icon size={20} color={s.color} strokeWidth={2} />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', marginBottom: '6px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '14px', fontWeight: 700, color: C.textPrimary }}>{s.title}</span>
                <span style={{ fontSize: '12px', color: s.color, fontWeight: 600 }}>{s.tagline}</span>
              </div>
              <div style={{
                fontSize: '13px', color: C.textSec, lineHeight: 1.65, fontStyle: 'italic',
                background: C.bg, borderRadius: '6px', padding: '10px 14px', marginBottom: '10px',
                borderLeft: `3px solid ${s.color}30`,
              }}>
                {s.scenario}
              </div>

            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

// ============================================================
// AI Insight Banner — human-in-loop guidance after results
// Alternate layout: stacked block, metric chips, no flex cramping
// ============================================================
const MetricChip = ({ value, label, color }) => (
  <div style={{
    display: 'inline-flex', flexDirection: 'column', alignItems: 'center',
    padding: '8px 16px', borderRadius: '8px',
    background: 'rgba(255,255,255,0.7)', border: `1px solid ${color}30`,
    minWidth: '72px',
  }}>
    <span style={{ fontSize: '20px', fontWeight: 800, color, lineHeight: 1 }}>{value}</span>
    <span style={{ fontSize: '10px', fontWeight: 600, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em', marginTop: '3px' }}>{label}</span>
  </div>
);

const AIInsightBanner = ({ service, data }) => {
  let insight = null;

  if (service === 'change-impact' && data?.change_entity) {
    const partCount = data.impacted_parts?.length || 0;
    const asmCount  = data.assembly_impact?.length || 0;
    const procCount = data.process_impacts?.length || 0;
    const reqCount  = data.impacted_requirements?.length || 0;
    const score     = data.impact_score || 0;
    const sev = score > 70 ? 'high' : score > 40 ? 'medium' : 'low';
    const color = sev === 'high' ? C.red : sev === 'medium' ? C.amber : C.green;
    const bg    = sev === 'high' ? C.redLight : sev === 'medium' ? C.amberLight : C.greenLight;
    const Icon  = sev === 'high' ? AlertTriangle : Info;
    const headline = sev === 'high' ? 'High-severity change — review carefully before approval'
      : sev === 'medium' ? 'Moderate impact — targeted review recommended'
      : 'Low impact — standard review applies';
    insight = {
      color, bg, Icon, headline,
      chips: [
        { value: partCount, label: 'Parts' },
        { value: asmCount,  label: 'Assemblies' },
        { value: reqCount,  label: 'Requirements' },
        { value: procCount, label: 'Processes' },
      ],
      cta: 'Use "View in Graph" to visually trace the impact path before signing off on the change.',
    };
  } else if (service === 'similar-parts' && data?.source_part) {
    const count = data.similar_parts?.length || 0;
    insight = {
      color: C.primary, bg: C.primaryLight, Icon: Info,
      headline: `${count} candidate part${count !== 1 ? 's' : ''} identified for reuse consideration`,
      chips: [{ value: count, label: 'Candidates' }],
      cta: 'Scoring weighs assembly co-occurrence (30%), traceability links (20%), type match (20%), RFLP layer (15%), and name similarity (15%). Validate before substituting.',
    };
  } else if (service === 'manufacturing' && data?.part) {
    const direct = data.process_summary?.total_direct    || 0;
    const inst   = data.process_summary?.total_instances || 0;
    const rel    = data.process_summary?.total_related   || 0;
    insight = {
      color: C.green, bg: C.greenLight, Icon: Info,
      headline: `Process landscape mapped — ${direct + inst + rel} total process${(direct + inst + rel) !== 1 ? 'es' : ''} identified`,
      chips: [
        { value: direct, label: 'Direct' },
        { value: inst,   label: 'Instances' },
        { value: rel,    label: 'Related' },
      ],
      cta: 'Validate the sequence against the manufacturing plan before use in production planning.',
    };
  }

  if (!insight) return null;
  const { color, bg, Icon, headline, chips, cta } = insight;
  return (
    <div style={{
      background: bg,
      borderRadius: '10px',
      borderLeft: `5px solid ${color}`,
      border: `1px solid ${color}20`,
      padding: '16px 20px 18px',
      marginBottom: '14px',
      width: '100%',
      boxSizing: 'border-box',
    }}>
      {/* Headline row — inline layout avoids flex shrink bug */}
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
        paddingTop: '12px', borderTop: `1px solid ${color}20`,
      }}>
        {cta}
      </div>
    </div>
  );
};

// ============================================================
// Main Component
// ============================================================
const RecommendationsTab = ({ setActiveTab }) => {
  const [activeService, setActiveService] = useState(null);
  const [inputValue, setInputValue] = useState('');
  const [topN, setTopN] = useState(10);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  // Listen for prefill events from graph tooltip recommendation buttons
  useEffect(() => {
    const handler = (e) => {
      const { service, nodeName } = e.detail || {};
      if (service && nodeName) {
        setActiveService(service);
        setInputValue(nodeName);
        setResult(null);
        setError('');
      }
    };
    window.addEventListener('dt-rec-prefill', handler);
    if (window.__dt_rec_prefill) {
      const { service, nodeName } = window.__dt_rec_prefill;
      if (service && nodeName) { setActiveService(service); setInputValue(nodeName); }
      delete window.__dt_rec_prefill;
    }
    return () => window.removeEventListener('dt-rec-prefill', handler);
  }, []);

  const handleAnalyse = useCallback(async () => {
    if (!inputValue.trim() || !activeService) return;
    setLoading(true); setError(''); setResult(null);
    try {
      let resp;
      if (activeService === 'change-impact') {
        resp = await API_METHODS.recommendations.changeImpact(inputValue.trim());
      } else if (activeService === 'similar-parts') {
        resp = await API_METHODS.recommendations.similarParts(inputValue.trim(), topN);
      } else if (activeService === 'manufacturing') {
        resp = await API_METHODS.recommendations.manufacturing(inputValue.trim());
      }
      setResult(resp.data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Request failed');
    } finally {
      setLoading(false);
    }
  }, [activeService, inputValue, topN]);

  const handleKeyDown = (e) => { if (e.key === 'Enter') handleAnalyse(); };

  const handleSelect = (id, prefill) => {
    setActiveService(id);
    if (prefill) setInputValue(prefill);
    setResult(null); setError('');
  };

  const services = [
    { id: 'change-impact',  Icon: Zap,     label: 'Change Impact',        color: C.orange  },
    { id: 'similar-parts',  Icon: Search,  label: 'Similar Parts',        color: C.primary },
    { id: 'manufacturing',  Icon: Factory, label: 'Manufacturing Process', color: C.green   },
  ];
  const active = services.find(s => s.id === activeService);

  return (
    <div style={{ padding: '20px', minHeight: '100%', overflowX: 'hidden', background: C.bg, boxSizing: 'border-box' }}>
      <style>{`@keyframes rec-spin { to { transform: rotate(360deg); } }`}</style>

      {/* Persistent service sub-tab bar — always visible */}
      <div style={{
        display: 'flex', gap: '0', marginBottom: '16px',
        borderBottom: `2px solid ${C.border}`, alignItems: 'flex-end',
        background: C.surface, borderRadius: '10px 10px 0 0',
        padding: '0 8px',
        boxShadow: '0 1px 4px rgba(0,0,0,0.06)',
      }}>
        {services.map(svc => {
          const isActive = activeService === svc.id;
          return (
            <button
              key={svc.id}
              onClick={() => handleSelect(svc.id)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '7px',
                padding: '12px 20px', border: 'none', background: 'transparent',
                borderBottom: isActive ? `3px solid ${svc.color}` : '3px solid transparent',
                color: isActive ? svc.color : C.textSec,
                fontSize: '13px', fontWeight: isActive ? 700 : 500,
                cursor: 'pointer', transition: 'all .15s ease', marginBottom: '-2px',
                whiteSpace: 'nowrap',
              }}
            >
              <svc.Icon size={14} strokeWidth={2.5} />
              {svc.label}
            </button>
          );
        })}
      </div>

      {/* Welcome scenario panel — shown when no service chosen */}
      {!activeService && <ScenarioPanel onSelect={handleSelect} />}

      {/* Input area */}
      {activeService && (
        <div style={CARD}>
          <div style={{ fontSize: '11px', color: C.textSec, marginBottom: '8px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
            {active?.label} — Enter name to analyse
          </div>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
            <input
              type="text"
              value={inputValue}
              onChange={e => setInputValue(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                activeService === 'change-impact' ? 'Input'
                : activeService === 'similar-parts' ? 'Input'
                : 'Input'
              }
              style={{
                flex: '1 1 300px', padding: '10px 14px', borderRadius: '7px',
                border: `1px solid ${C.borderDark}`, fontSize: '14px', outline: 'none', color: C.textPrimary,
              }}
              onFocus={e => { e.target.style.borderColor = C.primary; e.target.style.boxShadow = `0 0 0 3px ${C.primaryLight}`; }}
              onBlur={e => { e.target.style.borderColor = C.borderDark; e.target.style.boxShadow = 'none'; }}
            />
            {activeService === 'similar-parts' && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <label style={{ fontSize: '12px', color: C.textSec, fontWeight: 600 }}>Top N:</label>
                <input
                  type="number" min={1} max={50} value={topN}
                  onChange={e => setTopN(Number(e.target.value))}
                  style={{ width: '62px', padding: '9px 8px', borderRadius: '7px', border: `1px solid ${C.borderDark}`, fontSize: '14px' }}
                />
              </div>
            )}
            <button
              onClick={handleAnalyse}
              disabled={loading || !inputValue.trim()}
              style={{
                padding: '10px 22px', border: 'none', borderRadius: '7px',
                background: loading || !inputValue.trim() ? C.textMuted : C.primary,
                color: '#fff', fontSize: '14px', fontWeight: 600,
                cursor: loading || !inputValue.trim() ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', gap: '7px',
                transition: 'background .15s ease',
              }}
            >
              {loading ? (
                <>
                  <span style={{ width: 14, height: 14, border: '2px solid rgba(255,255,255,0.3)', borderTop: '2px solid #fff', borderRadius: '50%', animation: 'rec-spin 0.9s linear infinite', display: 'inline-block' }} />
                  Analysing…
                </>
              ) : 'Analyse'}
            </button>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ ...CARD, background: C.redLight, border: `1px solid ${C.red}30`, borderLeft: `4px solid ${C.red}`, color: C.red }}>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <AlertTriangle size={15} strokeWidth={2.5} />
            <strong>Error:</strong> {error}
          </div>
        </div>
      )}

      {/* AI Insight banner */}
      {result && <AIInsightBanner service={activeService} data={result} />}

      {/* Results */}
      {result && activeService === 'change-impact'  && <ChangeImpactResult  data={result} setActiveTab={setActiveTab} />}
      {result && activeService === 'similar-parts'  && <SimilarPartsResult  data={result} setActiveTab={setActiveTab} />}
      {result && activeService === 'manufacturing'  && <ManufacturingResult data={result} setActiveTab={setActiveTab} />}
    </div>
  );
};

// ============================================================
// Change Impact Result
// ============================================================
const ChangeImpactResult = ({ data, setActiveTab }) => {
  const [tab, setTab] = useState('overview');
  if (data.message && !data.change_entity) {
    return <div style={CARD}><em style={{ color: C.textSec }}>{data.message}</em></div>;
  }

  const ce = data.change_entity || {};
  const allNames = [
    ce.name,
    ...(data.impacted_parts || []).map(p => p.name),
    ...(data.assembly_impact || []).map(a => a.assembly_name),
    ...(data.realization_chain || []).map(r => r.name),
  ].filter(Boolean);

  const tabs = [
    { id: 'overview',      label: 'Overview',           color: C.orange  },
    { id: 'parts',         label: 'Impacted Parts',      color: C.orange,  count: data.impacted_parts?.length        || 0 },
    { id: 'assembly',      label: 'Assembly Impact',     color: C.primary, count: data.assembly_impact?.length       || 0 },
    { id: 'requirements',  label: 'Requirements',        color: C.amber,   count: data.impacted_requirements?.length || 0 },
    { id: 'processes',     label: 'Processes',           color: C.green,   count: data.process_impacts?.length       || 0 },
    { id: 'realization',   label: 'Realization Chain',   color: C.orange,  count: data.realization_chain?.length     || 0 },
  ];

  return (
    <div>
      {/* Header — always visible */}
      <div style={CARD}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '14px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
              <Zap size={17} color={C.orange} strokeWidth={2.5} />
              <span style={{ fontSize: '16px', fontWeight: 700, color: C.textPrimary }}>{ce.name}</span>
            </div>
            <div>
              <Badge color={C.red}>{ce.source_tag}</Badge>
              {ce.revision && <Badge color={C.textSec}>Rev {ce.revision}</Badge>}
            </div>
          </div>
          <div style={{ minWidth: '260px' }}>
            <div style={{ fontSize: '11px', color: C.textSec, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '6px' }}>Impact Score</div>
            <ScoreBar score={data.impact_score} />
          </div>
        </div>
        {allNames.length > 0 && <ViewGraphBtn names={allNames} setActiveTab={setActiveTab} />}
      </div>

      {/* Result sub-tabs */}
      <ResultTabBar tabs={tabs} active={tab} onChange={setTab} />

      {tab === 'overview' && <RadialImpactGraph data={data} />}

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
                    <td style={TD}><span style={{ fontWeight: 700, color: C.primary }}>{p.name}</span></td>
                    <td style={TD}><Badge color={C.primaryHover}>{p.source_tag || '—'}</Badge></td>
                    <td style={TD}><span style={{ fontWeight: 600, color: C.orange }}>{p.relation_type || '—'}</span></td>
                    <td style={TD}>{p.class_name || '—'}</td>
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
                    <td style={TD}><span style={{ fontWeight: 700, color: C.primary }}>{a.assembly_name}</span></td>
                    <td style={TD}><span style={{ fontWeight: 600, color: C.textSec }}>{a.depth}</span></td>
                    <td style={TD}>{a.from_part || '—'}</td>
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
                    <td style={TD}><span style={{ fontWeight: 700, color: C.amber }}>{r.name}</span></td>
                    <td style={TD}><Badge color={C.amber}>{r.catalogue_id || '—'}</Badge></td>
                    <td style={TD}><span style={{ color: C.primary, fontWeight: 600 }}>{r.linked_part || '—'}</span></td>
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
                    <td style={TD}><span style={{ fontWeight: 700, color: C.green }}>{p.name}</span></td>
                    <td style={TD}><Badge color={C.green}>{p.source_tag || '—'}</Badge></td>
                    <td style={TD}><span style={{ color: C.primary, fontWeight: 600 }}>{p.from_part || '—'}</span></td>
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
                    <td style={TD}><span style={{ fontWeight: 700, color: C.primary }}>{r.name}</span></td>
                    <td style={TD}><Badge color={C.orange}>{r.link_type || '—'}</Badge></td>
                    <td style={TD}><span style={{ color: C.primary, fontWeight: 600 }}>{r.from_part || '—'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No realization chain found.</div>
      )}
    </div>
  );
};

// ============================================================
// Similar Parts Result
// ============================================================
const SimilarPartsResult = ({ data, setActiveTab }) => {
  const [tab, setTab] = useState('overview');
  if (data.message && !data.source_part) {
    return <div style={CARD}><em style={{ color: C.textSec }}>{data.message}</em></div>;
  }

  const sp = data.source_part || {};
  const allNames = [sp.name, ...(data.similar_parts || []).map(p => p.name)].filter(Boolean);

  const tabs = [
    { id: 'overview', label: 'Overview',       color: C.primary },
    { id: 'results',  label: 'Similar Parts',   color: C.primary, count: data.similar_parts?.length || 0 },
  ];

  return (
    <div>
      {/* Header — always visible */}
      <div style={CARD}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <Search size={17} color={C.primary} strokeWidth={2.5} />
          <span style={{ fontSize: '15px', fontWeight: 700, color: C.textPrimary }}>
            Similar parts to: <span style={{ color: C.primary }}>{sp.name}</span>
          </span>
        </div>
        <div>
          <Badge color={C.primary}>{sp.source_tag}</Badge>
          {sp.rflp_layer && <Badge color={C.textSec}>{sp.rflp_layer}</Badge>}
          <span style={{ marginLeft: '10px', fontSize: '13px', color: C.textSec }}>{data.similar_parts?.length || 0} results</span>
        </div>
        {allNames.length > 1 && <ViewGraphBtn names={allNames} setActiveTab={setActiveTab} />}
      </div>

      <ResultTabBar tabs={tabs} active={tab} onChange={setTab} />

      {tab === 'overview' && (
        <div style={CARD}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px' }}>
            <div style={{ padding: '14px', borderRadius: '8px', background: C.primaryLight, textAlign: 'center' }}>
              <div style={{ fontSize: '28px', fontWeight: 800, color: C.primary }}>{data.similar_parts?.length || 0}</div>
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
                    <td style={TD}><span style={{ fontWeight: 700, color: C.primary }}>{p.name}</span></td>
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
            <div style={{ color: C.textSec }}>No similar parts found.</div>
          </div>
        )
      )}
    </div>
  );
};

// ============================================================
// Manufacturing Process Result
// ============================================================
const ManufacturingResult = ({ data, setActiveTab }) => {
  const [tab, setTab] = useState('overview');
  if (data.message && !data.part) {
    return <div style={CARD}><em style={{ color: C.textSec }}>{data.message}</em></div>;
  }

  const pt = data.part || {};
  const summary = data.process_summary || {};
  const allNames = [
    pt.name,
    ...(data.direct_processes || []).map(p => p.process_name),
    ...(data.process_instances || []).map(p => p.name),
  ].filter(Boolean);

  const tabs = [
    { id: 'overview',  label: 'Overview',           color: C.green  },
    { id: 'direct',    label: 'Direct Processes',    color: C.primary, count: data.direct_processes?.length          || 0 },
    { id: 'instances', label: 'Process Instances',   color: C.orange,  count: data.process_instances?.length         || 0 },
    { id: 'related',   label: 'Related Processes',   color: C.amber,   count: data.related_part_processes?.length    || 0 },
    { id: 'summary',   label: 'Type Summary',        color: C.primary  },
  ];

  return (
    <div>
      {/* Header — always visible */}
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
              <div style={{ fontSize: '22px', fontWeight: 700, color: C.primary }}>{summary.total_direct || 0}</div>
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
        {allNames.length > 1 && <ViewGraphBtn names={allNames} setActiveTab={setActiveTab} />}
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
                    <td style={TD}><Badge color={C.green}>{p.source_tag || '—'}</Badge></td>
                    <td style={TD}><span style={{ color: C.textSec, fontSize: '12px' }}>{p.file_name || '—'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No direct processes found.</div>
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
                    <td style={TD}><Badge color={C.orange}>{p.source_tag || '—'}</Badge></td>
                    <td style={TD}><span style={{ color: C.primary, fontWeight: 600 }}>{p.references_instance || '—'}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No process instances found.</div>
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
                    <td style={TD}><span style={{ color: C.primary, fontWeight: 600 }}>{p.part_name || '—'}</span></td>
                    <td style={TD}><Badge color={C.amber}>{p.relation || '—'}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No related processes found.</div>
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
                  <div style={{ fontSize: '13px', fontWeight: 700, color: C.primary }}>{type}</div>
                  <div style={{ fontSize: '22px', fontWeight: 700, color: C.textPrimary, margin: '4px 0' }}>{procs.length}</div>
                  <div style={{ fontSize: '11px', color: C.textSec, textTransform: 'uppercase' }}>processes</div>
                </div>
              ))}
            </div>
          </div>
        ) : <div style={{ ...CARD, color: C.textSec, textAlign: 'center', padding: '30px' }}>No process type summary available.</div>
      )}
    </div>
  );
};

// ============================================================
// Radial Impact Graph (D3) — concentric rings around change entity
// ============================================================
const RING_COLORS = [C.red, C.orange, C.amber, C.primary, C.green];

const RadialImpactGraph = ({ data }) => {
  const svgRef = useRef(null);

  useEffect(() => {
    if (!svgRef.current || !data?.change_entity) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    const width = svgRef.current.clientWidth || 600;
    const height = 420;
    const cx = width / 2, cy = height / 2;
    svg.attr('width', width).attr('height', height);

    const rings = [
      { label: 'Direct Impact',  items: (data.impacted_parts || []).map(p => p.name),                                    color: RING_COLORS[0] },
      { label: 'Assembly',       items: [...new Set((data.assembly_impact || []).map(a => a.assembly_name))].slice(0, 16), color: RING_COLORS[1] },
      { label: 'Requirements',   items: (data.impacted_requirements || []).map(r => r.name),                              color: RING_COLORS[2] },
      { label: 'Processes',      items: [...new Set((data.process_impacts || []).map(p => p.name))].slice(0, 16),         color: RING_COLORS[3] },
      { label: 'Realization',    items: (data.realization_chain || []).map(r => r.name),                                  color: RING_COLORS[4] },
    ].filter(r => r.items.length > 0);

    if (rings.length === 0) return;

    const maxRadius = Math.min(cx, cy) - 30;
    const ringStep = maxRadius / (rings.length + 1);
    const g = svg.append('g').attr('transform', `translate(${cx},${cy})`);

    // Tooltip div (appended to body for correct positioning)
    let radialTip = d3.select('body').select('.radial-tip');
    if (radialTip.empty()) {
      radialTip = d3.select('body').append('div').attr('class', 'radial-tip')
        .style('position', 'absolute').style('pointer-events', 'none')
        .style('background', 'rgba(26,43,60,0.92)').style('color', '#fff')
        .style('padding', '6px 12px').style('border-radius', '6px')
        .style('font-size', '12px').style('font-weight', '600')
        .style('z-index', '9999').style('opacity', '0')
        .style('transition', 'opacity .15s ease');
    }

    // Draw concentric rings
    rings.forEach((ring, ri) => {
      const r = ringStep * (ri + 1);
      g.append('circle')
        .attr('r', r)
        .attr('fill', 'none')
        .attr('stroke', ring.color)
        .attr('stroke-width', 1.5)
        .attr('stroke-dasharray', '6,4')
        .attr('opacity', 0.5);

      // Ring label
      g.append('text')
        .attr('x', r + 4)
        .attr('y', -4)
        .attr('font-size', 10)
        .attr('fill', ring.color)
        .attr('font-weight', 600)
        .text(`${ring.label} (${ring.items.length})`);

      // Distribute items around the ring
      ring.items.forEach((name, i) => {
        const angle = (2 * Math.PI * i) / ring.items.length - Math.PI / 2;
        const nx = r * Math.cos(angle);
        const ny = r * Math.sin(angle);

        // Line from center
        g.append('line')
          .attr('x1', 0).attr('y1', 0)
          .attr('x2', nx).attr('y2', ny)
          .attr('stroke', ring.color)
          .attr('stroke-width', 0.5)
          .attr('opacity', 0.25);

        // Node dot (interactive)
        g.append('circle')
          .attr('cx', nx).attr('cy', ny)
          .attr('r', 5)
          .attr('fill', ring.color)
          .attr('stroke', '#fff')
          .attr('stroke-width', 1.5)
          .style('cursor', 'pointer')
          .on('mouseover', function(event) {
            d3.select(this).attr('r', 9).attr('stroke-width', 2);
            radialTip
              .html(`<strong>${name}</strong><br/><span style="opacity:.7">${ring.label}</span>`)
              .style('left', (event.pageX + 12) + 'px')
              .style('top', (event.pageY - 28) + 'px')
              .style('opacity', '1');
          })
          .on('mousemove', function(event) {
            radialTip.style('left', (event.pageX + 12) + 'px').style('top', (event.pageY - 28) + 'px');
          })
          .on('mouseout', function() {
            d3.select(this).attr('r', 5).attr('stroke-width', 1.5);
            radialTip.style('opacity', '0');
          });

        // Label (show only if few items)
        if (ring.items.length <= 8) {
          g.append('text')
            .attr('x', nx)
            .attr('y', ny - 8)
            .attr('text-anchor', 'middle')
            .attr('font-size', 9)
            .attr('fill', C.textPrimary)
            .text(name.length > 20 ? name.slice(0, 18) + '…' : name);
        }
      });
    });

    // Center node — "CR" label (Change Request)
    g.append('circle').attr('r', 20).attr('fill', C.orange).attr('stroke', '#fff').attr('stroke-width', 2);
    g.append('text').attr('text-anchor', 'middle').attr('dy', 4)
      .attr('font-size', 9).attr('fill', '#fff').attr('font-weight', 700).text('CR');

    // Legend
    const legend = svg.append('g').attr('transform', `translate(10, ${height - 20 * rings.length - 10})`);
    rings.forEach((ring, i) => {
      const ly = i * 18;
      legend.append('circle').attr('cx', 6).attr('cy', ly).attr('r', 5).attr('fill', ring.color);
      legend.append('text').attr('x', 16).attr('y', ly + 4).attr('font-size', 11).attr('fill', C.textSec)
        .text(`${ring.label}: ${ring.items.length}`);
    });

  }, [data]);

  if (!data?.change_entity) return null;
  const hasAnyData = (data.impacted_parts?.length || data.assembly_impact?.length ||
    data.impacted_requirements?.length || data.process_impacts?.length || data.realization_chain?.length);
  if (!hasAnyData) return null;

  return (
    <div style={{ ...CARD, padding: '12px' }}>
      <SectionHeader icon={Target} label="Impact Radial View" color={C.orange} />
      <svg ref={svgRef} style={{ width: '100%', minHeight: '420px' }} />
    </div>
  );
};

// ============================================================
// Process Flow Timeline (D3) — grouped by process type
// ============================================================
const FLOW_COLORS = { direct: C.primary, instance: C.orange, related: C.amber };

const ProcessFlowTimeline = ({ data }) => {
  const svgRef = useRef(null);

  useEffect(() => {
    if (!svgRef.current || !data?.part) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    // Gather groups
    const groups = [];
    if (data.direct_processes?.length) groups.push({ label: 'Direct Processes', items: data.direct_processes.map(p => ({ name: p.process_name, tag: p.source_tag })), color: FLOW_COLORS.direct });
    if (data.process_instances?.length) groups.push({ label: 'Process Instances', items: data.process_instances.map(p => ({ name: p.name, tag: p.source_tag })), color: FLOW_COLORS.instance });
    if (data.related_part_processes?.length) groups.push({ label: 'Related Processes', items: data.related_part_processes.slice(0, 20).map(p => ({ name: p.process_name, tag: p.source_tag })), color: FLOW_COLORS.related });
    if (groups.length === 0) return;

    const itemH = 28, groupPad = 40, headerH = 30, leftPad = 160;
    const totalH = groups.reduce((h, g) => h + headerH + g.items.length * itemH + groupPad, 0) + 20;
    const width = svgRef.current.clientWidth || 700;
    svg.attr('width', width).attr('height', totalH);

    let yOffset = 15;
    const g = svg.append('g');

    // Central timeline line
    g.append('line')
      .attr('x1', leftPad - 10).attr('y1', 0)
      .attr('x2', leftPad - 10).attr('y2', totalH)
      .attr('stroke', C.border).attr('stroke-width', 2);

    groups.forEach((group) => {
      // Group header
      g.append('rect')
        .attr('x', 0).attr('y', yOffset)
        .attr('width', width - 20).attr('height', headerH)
        .attr('rx', 6)
        .attr('fill', group.color).attr('opacity', 0.1);
      g.append('text')
        .attr('x', 12).attr('y', yOffset + 20)
        .attr('font-size', 13).attr('font-weight', 700).attr('fill', group.color)
        .text(`${group.label} (${group.items.length})`);
      yOffset += headerH + 4;

      // Items
      group.items.forEach((item, i) => {
        const iy = yOffset + i * itemH;
        // Dot on timeline
        g.append('circle')
          .attr('cx', leftPad - 10).attr('cy', iy + itemH / 2)
          .attr('r', 5).attr('fill', group.color).attr('stroke', '#fff').attr('stroke-width', 1.5);
        // Connector line
        g.append('line')
          .attr('x1', leftPad - 5).attr('y1', iy + itemH / 2)
          .attr('x2', leftPad + 8).attr('y2', iy + itemH / 2)
          .attr('stroke', group.color).attr('stroke-width', 1).attr('opacity', 0.5);
        // Process card
        g.append('rect')
          .attr('x', leftPad + 10).attr('y', iy + 2)
          .attr('width', Math.min(width - leftPad - 40, 400)).attr('height', itemH - 5)
          .attr('rx', 4)
          .attr('fill', '#fff').attr('stroke', group.color).attr('stroke-width', 1);
        // Name
        g.append('text')
          .attr('x', leftPad + 18).attr('y', iy + itemH / 2 + 4)
          .attr('font-size', 11).attr('fill', C.textPrimary)
          .text(item.name?.length > 45 ? item.name.slice(0, 43) + '…' : item.name);
        // Tag badge
        if (item.tag) {
          const tagX = leftPad + Math.min(width - leftPad - 40, 400) - 5;
          g.append('text')
            .attr('x', tagX).attr('y', iy + itemH / 2 + 3)
            .attr('text-anchor', 'end')
            .attr('font-size', 9).attr('fill', group.color).attr('font-weight', 600)
            .text(item.tag);
        }
      });
      yOffset += group.items.length * itemH + groupPad;
    });
  }, [data]);

  if (!data?.part) return null;
  const hasAny = data.direct_processes?.length || data.process_instances?.length || data.related_part_processes?.length;
  if (!hasAny) return null;

  return (
    <div style={{ ...CARD, padding: '12px' }}>
      <SectionHeader icon={BarChart2} label="Process Flow Timeline" color={C.primary} />
      <svg ref={svgRef} style={{ width: '100%', minHeight: '200px' }} />
    </div>
  );
};

// 🔒 MEDIUM PRIORITY: Memoize component to prevent unnecessary re-renders
export default React.memo(RecommendationsTab, (prevProps, nextProps) => {
  // Only re-render if selectedNode or key data changes
  return (
    prevProps.selectedNode === nextProps.selectedNode &&
    prevProps.graphData === nextProps.graphData &&
    JSON.stringify(prevProps.recommendations) === JSON.stringify(nextProps.recommendations)
  );
});
