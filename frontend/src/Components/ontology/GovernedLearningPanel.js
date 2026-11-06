import React,{useEffect,useRef,useState} from 'react';
import {learningApi} from '../../services/learningApi';
import {getCredentialProfile} from '../../services/serviceAuth';
import {apiErrorMessage} from '../../utils/apiErrorMessage';
import './GovernedLearningPanel.css';

export default function GovernedLearningPanel({ontologyId,importTaskId,publication,preview,api=learningApi}){
 const [support,setSupport]=useState(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const [actor,setActor]=useState(''),[candidate,setCandidate]=useState(''),[result,setResult]=useState('confirmed'),[note,setNote]=useState('');
 const [outcome,setOutcome]=useState(null),[lesson,setLesson]=useState(null),[reason,setReason]=useState('');
 const epoch=useRef(0),controller=useRef(null),working=useRef(false);
 const scope=JSON.stringify([ontologyId,importTaskId,publication?.job_id||'']);
 const rows=(preview?.candidates||[]).filter(row=>publication?.approved_ids?.includes(row.candidate_id));
 const [credentials,setCredentials]=useState(0);
 useEffect(()=>{const reset=()=>setCredentials(value=>value+1);const events=['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired'];events.forEach(event=>window.addEventListener(event,reset));return()=>events.forEach(event=>window.removeEventListener(event,reset));},[]);
 function validateSupport(body){
   if(body?.ontology_id!==ontologyId||body?.import_task_id!==importTaskId||!Array.isArray(body?.lessons)||body.lessons.length>20||body.advisory_only!==true)throw new Error('Learning evidence changed the selected source.');
   if(body.lessons.some(row=>typeof row?.lesson_id!=='string'||typeof row?.review_hint!=='string'||typeof row?.mapping_pattern?.source_term!=='string'||typeof row?.mapping_pattern?.target_ontology_iri!=='string'))throw new Error('Learning evidence returned an invalid review hint.');
   return body;
 }
 useEffect(()=>{
   const stamp=++epoch.current;controller.current?.abort();working.current=false;
   setBusy(false);setError('');setSupport(null);setOutcome(null);setLesson(null);setCandidate('');setNote('');setReason('');
   const request=new AbortController();controller.current=request;
   if(ontologyId&&importTaskId&&getCredentialProfile('GRAPH_READ_TOKEN')){
     api.support(ontologyId,importTaskId,request.signal).then(response=>{
       if(stamp===epoch.current&&!request.signal.aborted)setSupport(validateSupport(response.data));
     }).catch(failure=>{if(stamp===epoch.current&&!request.signal.aborted)setError(apiErrorMessage(failure,'Approved review hints could not be checked.'));});
   }else setError('Select an imported instance and ontology, and connect read access in Admin to inspect review hints.');
   return()=>{++epoch.current;request.abort();controller.current?.abort();working.current=false;};
 },[scope,credentials,api,ontologyId,importTaskId]);
 const authorized=!!actor.trim()&&!!getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
 const identity=()=>({approved_by:actor.trim(),approval_token:getCredentialProfile('AGENTIC_APPROVAL_TOKEN')});
 async function run(operation){
   if(working.current)return;working.current=true;setBusy(true);setError('');
   controller.current?.abort();
   const stamp=epoch.current,request=new AbortController();controller.current=request;
   const current=()=>stamp===epoch.current&&!request.signal.aborted;
   try{await operation(request.signal,current);}catch(failure){if(current())setError(apiErrorMessage(failure,'Save was not confirmed. Retry the same review to recover its retained result.'));}
   finally{if(current()){working.current=false;setBusy(false);}}
 }
 return <section className="learning-review" aria-label="Governed mapping learning">
   <h3>Learning from reviewed mappings</h3>
   <p>Record what worked, review a lesson, then reuse it as a hint for this model revision. Hints do not train a model, change matching scores or approve publication.</p>
   <p>Feedback does not change published mappings. Apply corrections through the normal mapping review workflow.</p>
   {error&&<p role="alert">{error}</p>}
   <button type="button" disabled={busy||!ontologyId||!importTaskId} onClick={()=>run(async(signal,current)=>{const response=await api.support(ontologyId,importTaskId,signal);if(current())setSupport(validateSupport(response.data));})}>Refresh review hints</button>
   <label>Review name<input value={actor} maxLength={256} onChange={event=>setActor(event.target.value)} disabled={busy}/></label>
   {support?.lessons.length>0?<><label>Reason to revoke an existing hint<textarea value={reason} maxLength={1000} onChange={event=>setReason(event.target.value)} disabled={busy}/></label><table><thead><tr><th>Mapping pattern</th><th>Approved review hint</th><th>Human assessments</th><th>Review</th></tr></thead><tbody>{support.lessons.map(item=><tr key={item.lesson_id}><td>{item.mapping_pattern?.source_term} → {item.mapping_pattern?.target_ontology_iri}</td><td>{item.review_hint}</td><td>{item.measurements?.confirmed||0} confirmed; {item.measurements?.rejected||0} rejected; {item.measurements?.uncertain||0} uncertain</td><td><button type="button" disabled={busy||!authorized||!reason.trim()} onClick={()=>run(async(signal,current)=>{const response=await api.review(item.lesson_id,{...identity(),action:'revoke',reason},signal);if(current()){if(response.data?.lesson_id!==item.lesson_id||response.data.status!=='revoked')throw new Error('Revocation receipt did not match.');const refreshed=await api.support(ontologyId,importTaskId,signal);if(current())setSupport(validateSupport(refreshed.data));}})}>Revoke this hint</button></td></tr>)}</tbody></table></>:support&&<p>No approved hints for the current model revision.</p>}
   {!publication||publication.status!=='published'?<p>Publish and verify mappings before recording their outcomes.</p>:<>
     <label>Published mapping<select value={candidate} onChange={event=>{setCandidate(event.target.value);setOutcome(null);setLesson(null);}} disabled={busy||!!outcome}><option value="">Select a published mapping</option>{rows.map(row=><option key={row.candidate_id} value={row.candidate_id}>{row.source_term} → {row.ontology_term||row.target_ontology_iri}</option>)}</select></label>
     <label>Observed result<select value={result} onChange={event=>setResult(event.target.value)} disabled={busy||!!outcome}><option value="confirmed">Business meaning confirmed</option><option value="rejected">Business meaning rejected</option><option value="uncertain">Not yet established</option></select></label>
     <label>Review evidence<textarea value={note} maxLength={1000} onChange={event=>setNote(event.target.value)} disabled={busy||!!outcome}/></label>
     <button type="button" disabled={busy||!authorized||!candidate||!note.trim()||!!outcome} onClick={()=>run(async(signal,current)=>{
       const response=await api.outcome({...identity(),publication_id:publication.job_id,candidate_id:candidate,result,note},signal);
       if(current()){if(response.data?.kind!=='outcome'||response.data.publication_id!==publication.job_id||response.data.candidate_id!==candidate)throw new Error('Feedback receipt changed the selected mapping.');setOutcome(response.data);const refreshed=await api.support(ontologyId,importTaskId,signal);if(current())setSupport(validateSupport(refreshed.data));}
     })}>Save mapping feedback</button>
     {outcome&&<><p role="status">Feedback retained; publication receipt verified. Business correctness is your recorded assessment.</p><button type="button" disabled={busy||!authorized||!!lesson||outcome.result==='uncertain'} onClick={()=>run(async(signal,current)=>{
       const response=await api.prepare({...identity(),outcome_ids:[outcome.outcome_id]},signal);
       if(current()){if(response.data?.kind!=='lesson'||!response.data.outcome_ids?.includes(outcome.outcome_id))throw new Error('Lesson changed the selected outcome.');setLesson(response.data);}
     })}>Prepare review hint</button></>}
     {outcome&&<button type="button" disabled={busy} onClick={()=>{setOutcome(null);setLesson(null);setCandidate('');setNote('');setReason('');}}>Record another assessment</button>}
     {lesson&&<><p>{lesson.review_hint}</p><p>Review state: {lesson.status}. Based on {lesson.measurements?.assessments||0} human assessment(s); this is not a model accuracy score.</p><label>Approval or revocation reason<textarea value={reason} maxLength={1000} onChange={event=>setReason(event.target.value)} disabled={busy}/></label><button type="button" disabled={busy||!authorized||!reason.trim()||lesson.status==='revoked'} onClick={()=>run(async(signal,current)=>{
       const action=lesson.status==='approved'?'revoke':'approve';const response=await api.review(lesson.lesson_id,{...identity(),action,reason},signal);
       if(current()){if(response.data?.lesson_id!==lesson.lesson_id||response.data.status!==(action==='approve'?'approved':'revoked'))throw new Error('Lesson review receipt did not match.');setLesson(response.data);const refreshed=await api.support(ontologyId,importTaskId,signal);if(current())setSupport(validateSupport(refreshed.data));}
     })}>{lesson.status==='approved'?'Revoke review hint':'Approve review hint'}</button></>}
   </>}
 </section>;
}
