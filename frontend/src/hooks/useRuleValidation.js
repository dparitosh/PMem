import {useCallback,useEffect,useRef,useState} from 'react';
import {API_METHODS} from '../services/apiClient';
import {apiErrorMessage} from '../utils/apiErrorMessage';

export default function useRuleValidation(expression, ontologyId, view) {
 const request=useRef(null);
 const [validation,setValidation]=useState(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState(null);
 useEffect(()=>{
  request.current?.abort(); request.current=null;
  setValidation(null);setBusy(false);setError(null);
  return ()=>{request.current?.abort();request.current=null;};
 },[expression,ontologyId,view]);
 const validate=useCallback(async()=>{
  if(!expression.trim())return;
  request.current?.abort();const controller=new AbortController();request.current=controller;
  setValidation(null);setError(null);setBusy(true);
  try{
   const response=await API_METHODS.ontology.validateRule({rule:{rule_id:'ui-rule-preview',name:'UI rule preview',expression,use_case:'change_impact'}},
    {signal:controller.signal,timeout:30000});
   if(controller.signal.aborted || request.current!==controller)return;
   const result=response.data?.validation;
   if(!result || typeof result!=='object' || typeof result.valid!=='boolean')throw new Error('Rule service returned an invalid validation result.');
   setValidation(result);
  }catch(failure){if(!controller.signal.aborted && request.current===controller)setError(apiErrorMessage(failure,'Rule validation failed.'));}
  finally{if(!controller.signal.aborted && request.current===controller)setBusy(false);}
 },[expression,ontologyId,view]);
 return {validation,busy,error,validate};
}
