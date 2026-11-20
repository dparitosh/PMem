import React,{useEffect,useRef,useState} from 'react';
import {apiClient} from '../services/apiClient';
import {buildSemanticServiceUrl} from '../config';
import {getCredentialProfile} from '../services/serviceAuth';
import {apiErrorMessage} from '../utils/apiErrorMessage';

export default function AutomationEvidence({run}){
 const [state,setState]=useState({busy:false,evidence:null,error:''});
 const active=useRef(null);
 useEffect(()=>{
  const clear=()=>{active.current?.abort();setState({busy:false,evidence:null,error:''});};
  clear();const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-expired'];
  events.forEach(name=>window.addEventListener(name,clear));
  return()=>{active.current?.abort();events.forEach(name=>window.removeEventListener(name,clear));};
 },[run?.run_id]);
 async function inspect(){
  if(state.busy||!run?.run_id||!run.job_id||!run.job_version)return;
  const controller=new AbortController();active.current=controller;setState({busy:true,evidence:null,error:''});
  const planId=run.job_id+':'+run.job_version;
  const root=buildSemanticServiceUrl('oslc','/oslc/automation');
  const options={signal:controller.signal,headers:{Authorization:'Bearer '+getCredentialProfile('GRAPH_READ_TOKEN')}};
  try{
   const [plan,result]=await Promise.all([apiClient.get(root+'/plans/'+encodeURIComponent(planId),options),apiClient.get(root+'/results/'+encodeURIComponent(run.run_id),options)]);
   if(controller.signal.aborted)return;
   const value=result.data;
   if(plan.data?.identifier!==planId||plan.data?.type!=='oslc_auto:AutomationPlan'||value?.identifier!==run.run_id||value?.type!=='oslc_auto:AutomationResult'||typeof plan.data?.uri!=='string'||value['oslc_auto:reportsOnAutomationPlan']!==plan.data.uri||typeof value['oslc_auto:state']!=='string'||typeof value['oslc_auto:verdict']!=='string')throw new Error('Automation evidence does not match the selected workflow and run.');
   setState({busy:false,error:'',evidence:{plan:plan.data,result:value}});
  }catch(error){if(!controller.signal.aborted)setState({busy:false,evidence:null,error:apiErrorMessage(error)});}
 }
 const term=value=>String(value||'').replace('oslc_auto:','');
 return <section aria-label="Automation evidence"><button disabled={state.busy||!run?.run_id||!run.job_version} onClick={inspect}>{state.busy?'Checking automation evidence…':'Verify automation evidence'}</button>{state.error&&<p role="alert">{state.error}</p>}{state.evidence&&<><dl><dt>Automation plan</dt><dd>{state.evidence.plan.title} · {run.job_version}</dd><dt>Processing request</dt><dd>{run.run_number||'Selected run'}</dd><dt>Execution state</dt><dd>{term(state.evidence.result['oslc_auto:state'])}</dd><dt>Execution verdict</dt><dd>{term(state.evidence.result['oslc_auto:verdict'])}</dd></dl><p>Execution evidence only. CR/CO approval and publication are separate.</p></>}</section>;
}
