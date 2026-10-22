import DecisionPolicyAssessment from './DecisionPolicyAssessment';
import React, { useState, useCallback, useEffect, useRef, useId } from 'react';
import * as d3 from 'd3';
import {
  Zap, Search, Factory,
  BarChart2, Target,
  CheckCircle, Minus, AlertTriangle,
  Info,
} from 'lucide-react';
import { API_METHODS } from '../services/apiClient';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import './RecommendationsTab.css';
import ReadGoalPanel from './ReadGoalPanel';
import {agenticClient} from '../services/agenticApi';
import {buildSemanticServiceUrl} from '../config';
import {recommendationGoalEvidence,recommendationTask,recommendationTools} from '../utils/recommendationGoal';
import { UI_COLORS as C } from '../styles/uiTokens';

// Shared UI configuration
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
  color: C.primaryText,
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

// Shared UI configuration
const Badge = ({ color = C.primary, children }) => (
  <span style={{
    display: 'inline-block', padding: '2px 9px', borderRadius: '10px',
    fontSize: '11px', fontWeight: 600, background: color, color: '#fff',
    marginRight: '5px',
  }}>{children}</span>
);

const ScoreBar = ({ score, max = 100 }) => {
  if(typeof score!=='number'||!Number.isFinite(score))return <span>Impact score not recorded</span>;
  const pct = Math.max(0, Math.min((score / max) * 100, 100));
  const barColor = score > 70 ? C.red : score > 40 ? C.amber : C.green;
  const label = score > 70 ? 'High Impact' : score > 40 ? 'Medium Impact' : 'Low Impact';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
      <div style={{ flex: 1, height: '8px', background: C.border, borderRadius: '4px', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: barColor, borderRadius: '4px', transition: 'width .4s ease' }} />
      </div>
      <span style={{ fontSize: '12px', fontWeight: 700, color: barColor, minWidth: '100px', whiteSpace: 'nowrap' }}>
        {score} Ã¢â‚¬â€ {label}
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

// Shared UI configuration
const SectionHeader = ({ icon: Icon, label, count, color = C.primary }) => (
  <div style={{
    fontSize: '12px', fontWeight: 700, color: C.textPrimary, marginBottom: '12px',
    marginTop: '20px', display: 'flex', alignItems: 'center', gap: '8px',
    textTransform: 'uppercase', letterSpacing: '0.05em',
  }}>
    <Icon size={11} color={color} strokeWidth={2.2} />
    <span>{label}</span>
    {count !== undefined && (
      <span style={{
        background: C.primaryLight, color: C.primaryText,
        fontSize: '11px', fontWeight: 700, padding: '1px 8px', borderRadius: '10px',
      }}>{count}</span>
    )}
  </div>
);

const ResultEmptyState = ({
  icon: Icon = Info,
  title = 'No result details available',
  message = 'The service returned successfully, but there is no structured recommendation content to display yet.',
  color = C.textSec,
}) => (
  <div style={{ ...CARD, textAlign: 'center', padding: '30px' }}>
    <Icon size={24} color={color} style={{ display: 'block', margin: '0 auto 10px' }} />
    <div style={{ fontWeight: 700, color: C.textPrimary, marginBottom: '6px' }}>{title}</div>
    <div style={{ color: C.textSec, lineHeight: 1.6 }}>{message}</div>
  </div>
);

// Check / blank cell indicator
const CheckCell = ({ value }) => value
  ? <CheckCircle size={14} color={C.green} strokeWidth={2.5} />
  : <Minus size={13} color={C.textMuted} />;


const SERVICE_ALIASES = {
  impact: 'change-impact',
  'change_impact': 'change-impact',
  changeImpact: 'change-impact',
  similar: 'similar-parts',
  'similar_parts': 'similar-parts',
  similarParts: 'similar-parts',
  process: 'manufacturing',
  manufacturing: 'manufacturing',
  mfg: 'manufacturing',
};

const normalizeRecommendationService = (service) => {
  const key = String(service || '').trim();
  return SERVICE_ALIASES[key] || key;
};

const extractRecommendationInput = (detail = {}) => (
  detail.nodeName ||
  detail.name ||
  detail.label ||
  detail.displayName ||
  detail.value ||
  detail.query ||
  detail.partName ||
  detail.changeName ||
  ''
);

const normalizeRecommendationResult = (service, payload) => {
  const data = payload || {};
  if (service === 'change-impact') {
    return {
      ...data,
      impacted_parts: Array.isArray(data.impacted_parts) ? data.impacted_parts : [],
      assembly_impact: Array.isArray(data.assembly_impact) ? data.assembly_impact : [],
      impacted_requirements: Array.isArray(data.impacted_requirements) ? data.impacted_requirements : [],
      process_impacts: Array.isArray(data.process_impacts) ? data.process_impacts : [],
      realization_chain: Array.isArray(data.realization_chain) ? data.realization_chain : [],
    };
  }
  if (service === 'similar-parts') {
    return {
      ...data,
      similar_parts: Array.isArray(data.similar_parts) ? data.similar_parts : [],
    };
  }
  if (service === 'manufacturing') {
    return {
      ...data,
      direct_processes: Array.isArray(data.direct_processes) ? data.direct_processes : [],
      process_instances: Array.isArray(data.process_instances) ? data.process_instances : [],
      related_part_processes: Array.isArray(data.related_part_processes) ? data.related_part_processes : Array.isArray(data.related_processes) ? data.related_processes : [],
      process_summary: data.process_summary || {},
    };
  }
  return data;
};

// ============================================================
// Shared UI configuration
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

// ============================================================
// Shared UI configuration
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
    const score     = data.impact_score;
    const hasScore=typeof score==='number'&&Number.isFinite(score);
    const sev = score > 70 ? 'high' : score > 40 ? 'medium' : 'low';
    const color = sev === 'high' ? C.red : sev === 'medium' ? C.amber : C.green;
    const bg    = sev === 'high' ? C.redLight : sev === 'medium' ? C.amberLight : C.greenLight;
    const Icon  = sev === 'high' ? AlertTriangle : Info;
    const headline = !hasScore?'Impact evidence (score not recorded)':sev === 'high' ? 'High impact'
      : sev === 'medium' ? 'Moderate impact'
      : 'Low impact';
    insight = {
      color, bg, Icon, headline,
      chips: [
        { value: partCount, label: 'Parts' },
        { value: asmCount,  label: 'Assemblies' },
        { value: reqCount,  label: 'Requirements' },
        { value: procCount, label: 'Processes' },
      ],
      cta: 'Check impacted areas before approval.',
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
      border: `1px solid ${color}20`,
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
const RecommendationsTab = () => {
  const [activeService, setActiveService] = useState('change-impact');
  const serviceTabs=useRef([]);
  const tabId=useId();
  const [inputValue, setInputValue] = useState('');
  const analysisGeneration = useRef(0);
  const analysisController = useRef(null);

  const [topN, setTopN] = useState(10);
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthRevision, setHealthRevision] = useState(0);
  const [quickResult, setResult] = useState(null);
  const [executionMode,setExecutionMode]=useState('agent');
  const [agentRun,setAgentRun]=useState(null);
  const [agentContract,setAgentContract]=useState(false);
  const [agentTools,setAgentTools]=useState(null);
  const [agentError,setAgentError]=useState('');
  const [error, setError] = useState('');

  useEffect(() => { analysisController.current?.abort(); analysisGeneration.current += 1; setResult(null); setAgentRun(null); setError(''); setLoading(false); }, [activeService, inputValue, topN]);

  useEffect(()=>{
    const controller=new AbortController();setAgentTools(null);setAgentContract(false);setAgentError('');
    agenticClient.get(buildSemanticServiceUrl('agentic','/api/v1/tools'),{signal:controller.signal,timeout:15000}).then(response=>{
      if(!controller.signal.aborted){setAgentTools(new Set((response.data?.tools||[]).map(tool=>tool.id)));setAgentContract(response.data?.read_goal_capabilities?.recommendation_evidence===1);}
    }).catch(failure=>{if(!controller.signal.aborted)setAgentError(apiErrorMessage(failure,'Agent tools are unavailable.'));});
    return()=>controller.abort();
  },[healthRevision]);
  const goalContext={page:'quality',recommendation_service:activeService,recommendation_object:inputValue.trim(),recommendation_top_n:topN};
  const result=executionMode==='agent'?recommendationGoalEvidence(agentRun,goalContext):quickResult;
  const recommendationReady = !healthLoading && health?.status === 'ok' && health?.readiness?.scenario_ready === true;
  const readinessMessage = health?.readiness?.message || health?.error || (
    healthLoading ? 'Checking recommendation readiness...' : 'Recommendation readiness is unavailable.'
  );
  const activeServiceReadiness = activeService ? health?.readiness?.service_readiness?.[activeService] : null;

  useEffect(() => {
    let cancelled = false;
    setHealthLoading(true);
    const controller = new AbortController();
    API_METHODS.recommendations.health({ signal: controller.signal, timeout: 15000 })
      .then(resp => {
        if (!cancelled) setHealth(resp.data);
      })
      .catch(err => {
        if (!cancelled) {
          setHealth({
            status: 'degraded',
            readiness: {
              scenario_ready: false,
              message: apiErrorMessage(err, 'Recommendation service is not reachable.'),
            },
          });
        }
      })
      .finally(() => {
        if (!cancelled) setHealthLoading(false);
      });
    return () => { cancelled = true; controller.abort(); };
  }, [healthRevision]);

  useEffect(() => {
    const resetSession = () => {
      analysisController.current?.abort();
      analysisGeneration.current += 1;
      setResult(null);
      setAgentRun(null);
      setError('');
      setLoading(false);
      setHealth(null);
      setHealthLoading(true);
      setHealthRevision(value => value + 1);
    };
    window.addEventListener('depo:credentials-changed', resetSession);
    window.addEventListener('depo:credentials-cleared', resetSession);
    return () => {
      window.removeEventListener('depo:credentials-changed', resetSession);
      window.removeEventListener('depo:credentials-cleared', resetSession);
      analysisController.current?.abort();
      analysisGeneration.current += 1;
    };
  }, []);

  // Listen for prefill events from graph tooltip recommendation buttons
  useEffect(() => {
    const applyPrefill = (detail = {}) => {
      const service = normalizeRecommendationService(detail.service);
      const input = extractRecommendationInput(detail);
      if (['change-impact','similar-parts','manufacturing'].includes(service) && input) {
        setActiveService(service);
        setInputValue(input);
        setResult(null);
        setError('');
      }
    };

    const handler = (e) => applyPrefill(e.detail || {});
    window.addEventListener('dt-rec-prefill', handler);
    window.addEventListener('dt-recommendation-prefill', handler);
    if (window.__dt_rec_prefill) {
      applyPrefill(window.__dt_rec_prefill);
      delete window.__dt_rec_prefill;
    }
    return () => {
      window.removeEventListener('dt-rec-prefill', handler);
      window.removeEventListener('dt-recommendation-prefill', handler);
    };
  }, []);

  const handleAnalyse = useCallback(async () => {
    const generation = ++analysisGeneration.current;
    if (!inputValue.trim() || !activeService) return;
    if (!recommendationReady || activeServiceReadiness===false || activeServiceReadiness?.ready===false) { setLoading(false); setError('Verify recommendation readiness before analysis.'); return; }
    if(activeService==='similar-parts'&&(!Number.isInteger(topN)||topN<1||topN>50)){setError('Choose a whole number of results from 1 to 50.');return;}
    analysisController.current?.abort();
    const controller = new AbortController();
    analysisController.current = controller;
    setLoading(true); setError(''); setResult(null);
    try {
      let resp;
      if (activeService === 'change-impact') {
        resp = await API_METHODS.recommendations.changeImpact(inputValue.trim(), {}, { signal: controller.signal, timeout:60000 });
      } else if (activeService === 'similar-parts') {
        resp = await API_METHODS.recommendations.similarParts(inputValue.trim(), topN, {}, { signal: controller.signal, timeout:60000 });
      } else if (activeService === 'manufacturing') {
        resp = await API_METHODS.recommendations.manufacturing(inputValue.trim(), {}, { signal: controller.signal, timeout:60000 });
      }
      if (generation === analysisGeneration.current) setResult(normalizeRecommendationResult(activeService, resp.data));
    } catch (err) {
      if (generation === analysisGeneration.current) setError(apiErrorMessage(err));
    } finally {
      if (generation === analysisGeneration.current) setLoading(false);
    }
  }, [activeService, inputValue, topN, recommendationReady, activeServiceReadiness]);

  useEffect(() => () => { analysisGeneration.current += 1; }, []);


  const handleSelect = (id, prefill) => {
    setActiveService(normalizeRecommendationService(id));
    if (prefill) setInputValue(prefill);
    setResult(null); setError('');
  };

  const services = [
    { id: 'change-impact',  Icon: Zap,     label: 'Change Impact',        color: C.orange  },
    { id: 'similar-parts',  Icon: Search,  label: 'Similar Parts',        color: C.primaryText },
    { id: 'manufacturing',  Icon: Factory, label: 'Process Context', color: C.green   },
  ];
  const canAnalyse=recommendationReady&&activeServiceReadiness!==false&&activeServiceReadiness?.ready!==false;
  const selectedService=services.find(service=>service.id===activeService);
  const navigate=(event,index)=>{
    const next=event.key==='Home'?0:event.key==='End'?services.length-1:event.key==='ArrowRight'?(index+1)%services.length:event.key==='ArrowLeft'?(index+services.length-1)%services.length:null;
    if(next===null)return;
    event.preventDefault();handleSelect(services[next].id);serviceTabs.current[next]?.focus();
  };
  return <section className="recommendation-cockpit" aria-label="Graph recommendations">
    <header className="recommendation-heading"><div><span className="recommendation-eyebrow">Decision support</span><h2>Recommendations</h2><p>Choose an analysis, identify a graph object, then review the evidence before making a decision.</p></div><button type="button" disabled={healthLoading} onClick={()=>setHealthRevision(value=>value+1)}>{healthLoading?'Checking readiness…':'Retry recommendation readiness'}</button></header>
    <div className="recommendation-readiness" role="status"><span className={`recommendation-readiness__badge ${recommendationReady?'is-ready':''}`}>{healthLoading?'Checking':recommendationReady?'Graph ready':'Needs attention'}</span><span>{readinessMessage}</span>{!healthLoading&&!recommendationReady&&<a href="#/import">Review source imports</a>}</div>
    <div className="recommendation-services" role="tablist" aria-label="Recommendation analyses">{services.map((service,index)=><button key={service.id} type="button" role="tab" id={`${tabId}-${service.id}`} aria-controls={`${tabId}-analysis`} aria-selected={activeService===service.id} tabIndex={activeService===service.id?0:-1} ref={node=>{serviceTabs.current[index]=node;}} onClick={()=>handleSelect(service.id)} onKeyDown={event=>navigate(event,index)}><service.Icon size={17} aria-hidden="true"/>{service.label}</button>)}</div>
    <section role="tabpanel" id={`${tabId}-analysis`} aria-labelledby={`${tabId}-${activeService}`} tabIndex={0}>
      <p className="recommendation-purpose">{activeService==='change-impact'?'Trace downstream parts, assemblies, requirements and processes affected by a change.':activeService==='similar-parts'?'Compare an existing part with graph candidates to assess possible reuse.':'Inspect process links and operational context around a part or assembly.'}</p>
      {recommendationReady&&(activeServiceReadiness===false||activeServiceReadiness?.ready===false)&&<p role="status" className="recommendation-notice">{activeServiceReadiness?.message||'This analysis is not ready. Review source graph data and retry readiness.'}</p>}
      <div className="recommendation-mode"><label>Analysis method<select value={executionMode} onChange={event=>{analysisController.current?.abort();analysisGeneration.current+=1;setLoading(false);setResult(null);setExecutionMode(event.target.value);}}><option value="agent">Agent investigation + Semantica review</option><option value="graph">Direct graph analysis</option></select></label><p>{executionMode==='agent'?'The existing Graph Analyst plans read steps, retains observations and explains graph evidence with the shared decision-policy assessment.':'Run the bounded graph query directly, with the same shared decision-policy assessment.'}</p></div>
      <form className="recommendation-query" onSubmit={event=>{event.preventDefault();if(executionMode==='graph')handleAnalyse();}}>
        <label>{activeService==='change-impact'?'Changed item':activeService==='similar-parts'?'Reference part':'Part or assembly'}<input value={inputValue} onChange={event=>setInputValue(event.target.value)} placeholder="Enter an existing graph object name" autoComplete="off"/></label>
        {activeService==='similar-parts'&&<label className="recommendation-query__limit">Results<input type="number" min="1" max="50" step="1" value={topN} onChange={event=>setTopN(event.target.value===''?'':Number(event.target.value))}/></label>}
        {executionMode==='graph'&&<button type="submit" disabled={loading||!inputValue.trim()||!canAnalyse}>{loading?'Analysing…':'Analyse'}</button>}
      </form>
      {executionMode==='agent'&&<>
        {agentError&&<p role="alert">{agentError}</p>}
        {agentTools&&(!agentContract||!agentTools.has(recommendationTools[activeService]))&&<p role="status">Agent investigation is awaiting the updated PMem backend. Restart PMem, then retry readiness. Direct graph analysis remains available when graph context is ready.</p>}
        <ReadGoalPanel agent="graph-analyst" task={inputValue.trim()?recommendationTask(goalContext):''} context={goalContext} compact startLabel="Analyse with agent" disabled={!canAnalyse||!inputValue.trim()||!Number.isInteger(topN)||topN<1||topN>50||!agentContract||!agentTools?.has(recommendationTools[activeService])} onRunChange={setAgentRun}/>
      </>}
      {error&&<div role="alert" className="recommendation-notice recommendation-notice--error">{error}</div>}
      {loading&&<p role="status">Reading graph context for {inputValue}. Changing the object or analysis cancels this request.</p>}
      {!result&&!loading&&!error&&!(executionMode==='agent'&&agentRun)&&<div className="recommendation-empty"><strong>{inputValue?'Ready to analyse':'Start with a graph object'}</strong><p>{inputValue?'Run the analysis to inspect matching evidence.':'Copy an object name from Graph Explorer, or open a recommendation from its object actions.'}</p><a href="#/graph">Find an object in Graph Explorer</a></div>}
      {result&&<section className="recommendation-results" aria-label="Recommendation evidence"><div className="recommendation-result-heading"><h3>{selectedService.label} results</h3><span>Object: {inputValue}</span></div><AIInsightBanner service={activeService} data={result}/><details className="recommendation-method"><summary>Analysis method & scope</summary><p>{result.traceability || result.ranking_scope || 'Graph-derived read-only analysis. The response does not record additional method or coverage details.'}</p><p>Scores are heuristics, not calibrated confidence. The graph tool returns evidence and a shared decision-policy assessment. In agent mode, the existing Graph Analyst plans the investigation and cites the retained tool observation.</p></details><DecisionPolicyAssessment report={result.decision_policy}/>
        {activeService==='change-impact'&&<ChangeImpactResult data={result}/>}
        {activeService==='similar-parts'&&<SimilarPartsResult data={result}/>}
        {activeService==='manufacturing'&&<ManufacturingResult data={result}/>}
      </section>}
    </section>
    <p className="recommendation-review-note">Results reflect the available graph, not a complete engineering approval. Review source links, scores and decision-policy findings; agent conclusions and policy findings support review; neither analysis method approves or publishes changes.</p>
  </section>;

};

// ============================================================
// Change Impact Result
// ============================================================
const ChangeImpactResult = ({ data }) => {
  const [tab, setTab] = useState('overview');
  if (data.message && !data.change_entity) {
    return <div style={CARD}><em style={{ color: C.textSec }}>{data.message}</em></div>;
  }

  const ce = data.change_entity || {};
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
                    <td style={TD}><span style={{ fontWeight: 700, color: C.primaryText }}>{p.name}</span></td>
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
                    <td style={TD}><span style={{ fontWeight: 700, color: C.primaryText }}>{a.assembly_name}</span></td>
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
                    <td style={TD}><span style={{ fontWeight: 700, color: C.amber }}>{r.name}</span></td>
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
                    <td style={TD}><span style={{ fontWeight: 700, color: C.green }}>{p.name}</span></td>
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
                    <td style={TD}><span style={{ fontWeight: 700, color: C.primaryText }}>{r.name}</span></td>
                    <td style={TD}><Badge color={C.orange}>{r.link_type || 'Ã¢â‚¬â€'}</Badge></td>
                    <td style={TD}><span style={{ color: C.primaryText, fontWeight: 600 }}>{r.from_part || 'Ã¢â‚¬â€'}</span></td>
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

// ============================================================
// Manufacturing Process Result
// ============================================================
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

// ============================================================
// Shared UI configuration
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
              // Names come from graph/import data. Use D3 text binding rather
              // than HTML interpolation so a source value cannot execute.
              .text(`${name}\n${ring.label}`)
              .style('white-space', 'pre-line')
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
            .text(name.length > 20 ? name.slice(0, 18) + 'Ã¢â‚¬Â¦' : name);
        }
      });
    });

    // Shared UI configuration
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

  if (!data?.change_entity) {
    return (
      <ResultEmptyState
        icon={Target}
        title="No radial impact view available"
        message={data?.message || 'The change-impact response did not include a structured change entity for radial visualization.'}
        color={C.orange}
      />
    );
  }
  const hasAnyData = (data.impacted_parts?.length || data.assembly_impact?.length ||
    data.impacted_requirements?.length || data.process_impacts?.length || data.realization_chain?.length);
  if (!hasAnyData) {
    return (
      <ResultEmptyState
        icon={Target}
        title="No radial impact view available"
        message="The change-impact response loaded successfully, but there are no impacted nodes to visualize in the radial view."
        color={C.orange}
      />
    );
  }

  return (
    <div style={{ ...CARD, padding: '12px' }}>
      <SectionHeader icon={Target} label="Impact Radial View" color={C.orange} />
      <svg ref={svgRef} style={{ width: '100%', minHeight: '420px' }} />
    </div>
  );
};

// ============================================================
// Shared UI configuration
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
          .text(item.name?.length > 45 ? item.name.slice(0, 43) + 'Ã¢â‚¬Â¦' : item.name);
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

  if (!data?.part) {
    return (
      <ResultEmptyState
        icon={BarChart2}
        title="No process timeline available"
        message={data?.message || 'The manufacturing response did not include a structured part for timeline rendering.'}
        color={C.green}
      />
    );
  }
  const hasAny = data.direct_processes?.length || data.process_instances?.length || data.related_part_processes?.length;
  if (!hasAny) {
    return (
      <ResultEmptyState
        icon={BarChart2}
        title="No process timeline available"
        message="The manufacturing response loaded successfully, but there are no direct, instance, or related processes to draw in the timeline."
        color={C.green}
      />
    );
  }

  return (
    <div style={{ ...CARD, padding: '12px' }}>
      <SectionHeader icon={BarChart2} label="Process Flow Timeline" color={C.primary} />
      <svg ref={svgRef} style={{ width: '100%', minHeight: '200px' }} />
    </div>
  );
};

// Shared UI configuration
export default RecommendationsTab;
