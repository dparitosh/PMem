import { ManufacturingResult } from "./ManufacturingResult.js";
import { SimilarPartsResult } from "./SimilarPartsResult.js";
import { ChangeImpactResult } from "./ChangeImpactResult.js";
import { AIInsightBanner } from "./AIInsightBanner.js";

import { normalizeRecommendationService, extractRecommendationInput, normalizeRecommendationResult } from "./services/recommendationPresentation.js";
import DecisionPolicyAssessment from "../../Components/DecisionPolicyAssessment";
import React, { useState, useCallback, useEffect, useRef, useId } from 'react';

import { Zap, Search, Factory } from "lucide-react";
import { API_METHODS } from "../../services/apiClient";
import { apiErrorMessage } from "../../utils/apiErrorMessage";
import "./RecommendationsWorkspace.css";
import ReadGoalPanel from "../../Components/ReadGoalPanel";
import {agenticClient} from "../../services/agenticApi";
import {buildSemanticServiceUrl} from "../../config";
import {recommendationGoalEvidence,recommendationTask,recommendationTools} from "../../utils/recommendationGoal";
import { UI_COLORS as C } from "../../styles/uiTokens";

// Check / blank cell indicator

// ============================================================
// Main Component
// ============================================================
const RecommendationsWorkspace = () => {
  const [activeService, setActiveService] = useState('change-impact');
  const serviceTabs=useRef([]);
  const tabId=useId();
  const [inputValue, setInputValue] = useState('');
  const [objectContext, setObjectContext] = useState({});
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

  useEffect(() => { analysisController.current?.abort(); analysisGeneration.current += 1; setResult(null); setAgentRun(null); setError(''); setLoading(false); }, [activeService, inputValue, topN, objectContext]);

  useEffect(()=>{
    const controller=new AbortController();setAgentTools(null);setAgentContract(false);setAgentError('');
    agenticClient.get(buildSemanticServiceUrl('agentic','/api/v1/tools'),{signal:controller.signal,timeout:15000}).then(response=>{
      if(!controller.signal.aborted){setAgentTools(new Set((response.data?.tools||[]).map(tool=>tool.id)));setAgentContract(response.data?.read_goal_capabilities?.recommendation_evidence===1);}
    }).catch(failure=>{if(!controller.signal.aborted)setAgentError(apiErrorMessage(failure,'Agent tools are unavailable.'));});
    return()=>controller.abort();
  },[healthRevision]);
  const goalContext={page:'recommendations',...objectContext,recommendation_service:activeService,recommendation_object:inputValue.trim(),recommendation_top_n:topN};
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
    window.addEventListener('depo:session-expired', resetSession);
    return () => {
      window.removeEventListener('depo:credentials-changed', resetSession);
      window.removeEventListener('depo:credentials-cleared', resetSession);
      window.removeEventListener('depo:session-expired', resetSession);
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
        const context = {...(detail.scope || {}), ...detail};
        setObjectContext(Object.fromEntries(['node_id','ontology_id','ontology_prefix'].map(key => [key, context[key] || (key === 'node_id' ? context.elementId : key === 'ontology_prefix' ? context.prefix : '')]).filter(([,value]) => typeof value === 'string' && value.length > 0 && value.length <= 256)));
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
        resp = await API_METHODS.recommendations.changeImpact(inputValue.trim(), objectContext, { signal: controller.signal, timeout:60000 });
      } else if (activeService === 'similar-parts') {
        resp = await API_METHODS.recommendations.similarParts(inputValue.trim(), topN, objectContext, { signal: controller.signal, timeout:60000 });
      } else if (activeService === 'manufacturing') {
        resp = await API_METHODS.recommendations.manufacturing(inputValue.trim(), objectContext, { signal: controller.signal, timeout:60000 });
      }
      if (generation === analysisGeneration.current) setResult(normalizeRecommendationResult(activeService, resp.data));
    } catch (err) {
      if (generation === analysisGeneration.current) setError(apiErrorMessage(err));
    } finally {
      if (generation === analysisGeneration.current) setLoading(false);
    }
  }, [activeService, inputValue, topN, objectContext, recommendationReady, activeServiceReadiness]);

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
      <p className="recommendation-purpose">{activeService==='change-impact'?'Review dependency paths across parts, assemblies, requirements and processes, including configuration and effectivity questions.':activeService==='similar-parts'?'Compare typed parts using engineering properties, units and name similarity. Inspect conflicts and missing evidence before deciding on reuse.':'Inspect process links and operational context around a part or assembly.'}</p>
      {recommendationReady&&(activeServiceReadiness===false||activeServiceReadiness?.ready===false)&&<p role="status" className="recommendation-notice">{activeServiceReadiness?.message||'This analysis is not ready. Review source graph data and retry readiness.'}</p>}
      <div className="recommendation-mode"><label>Analysis method<select value={executionMode} onChange={event=>{analysisController.current?.abort();analysisGeneration.current+=1;setLoading(false);setResult(null);setExecutionMode(event.target.value);}}><option value="agent">Agent investigation + Semantica review</option><option value="graph">Direct graph analysis</option></select></label><p>{executionMode==='agent'?'The existing Graph Analyst plans read steps, retains observations and explains graph evidence with the shared decision-policy assessment.':'Run the bounded graph query directly, with the same shared decision-policy assessment.'}</p></div>
      <form className="recommendation-query" onSubmit={event=>{event.preventDefault();if(executionMode==='graph')handleAnalyse();}}>
        <label>{activeService==='change-impact'?'Changed item':activeService==='similar-parts'?'Reference part':'Part or assembly'}<input value={inputValue} onChange={event=>{setObjectContext({});setInputValue(event.target.value);}} placeholder="Enter an existing graph object name" autoComplete="off"/></label>
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

export default RecommendationsWorkspace;
