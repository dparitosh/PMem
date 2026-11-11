import React,{useEffect,useRef,useState} from 'react';
import {createPortal} from 'react-dom';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import './ActionReviewDialog.css';

export default function ActionReviewDialog({action,onClose,onConfirm,approver,onApproverChange,children,blockedReason,onResolve,resolveLabel}){
 const panel=useRef(null),close=useRef(null),lock=useRef(false),mounted=useRef(true);
 const [phase,setPhase]=useState('review'),[error,setError]=useState(''),[result,setResult]=useState(null);
 const busy=phase==='submitting';
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
 useEffect(()=>{
  const previous=document.activeElement,overflow=document.body.style.overflow;
  document.body.style.overflow='hidden';close.current?.focus();
  return()=>{document.body.style.overflow=overflow;if(previous?.isConnected)previous.focus();};
 },[]);
 const keys=event=>{
  if(event.key==='Escape'){event.preventDefault();if(!busy)onClose();return;}
  if(event.key!=='Tab')return;
  const controls=[...panel.current.querySelectorAll('button,a[href],input,select,textarea,summary,[tabindex="0"]')].filter(node=>!node.disabled);
  const first=controls[0],last=controls[controls.length-1];
  if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
  else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
 };
 const submit=async()=>{
  if(lock.current||phase==='accepted'||blockedReason)return;
  lock.current=true;setPhase('submitting');setError('');
  try{
   const receipt=await onConfirm(action);
   if(mounted.current){setResult(receipt||{});setPhase('accepted');}
  }catch(failure){if(mounted.current){setError(apiErrorMessage(failure,'The action was not confirmed. Check retained status before retrying.'));setPhase(action.retryable===false||failure?.actionBlocked||[400,403,404,409,422].includes(failure?.response?.status)?'unconfirmed':'review');}}
  finally{lock.current=false;}
 };
 return createPortal(<div className="action-review-overlay" onClick={event=>{if(event.target===event.currentTarget&&!busy)onClose();}}>
  <section className="action-review" role="dialog" aria-modal="true" aria-labelledby="action-review-title" onKeyDown={keys} ref={panel}>
   <header><div><span className="action-review__eyebrow">Review exact action</span><h2 id="action-review-title">{action.label}</h2><p>{action.name}</p></div><button ref={close} type="button" disabled={busy} onClick={onClose} aria-label="Close action review">×</button></header>
   <div className="action-review__body">
    <dl className="action-review__identity">{action.items.map(([label,value])=><React.Fragment key={label}><dt>{label}</dt><dd>{value===undefined||value===null||value===''?'Not recorded':String(value)}</dd></React.Fragment>)}</dl>
    <section className="action-review__scope"><h3>What this action does</h3><p>{action.description}</p></section>
    {blockedReason&&phase!=='accepted'&&<section className="action-review__error" role="status"><h3>Replay unavailable</h3><p>{blockedReason}</p><p>A completed historical run does not authorize a new execution.</p></section>}
    {phase!=='accepted'&&!blockedReason&&<>{onApproverChange&&<label className="action-review__approver">Action approver<input value={approver} onChange={event=>onApproverChange(event.target.value)} autoComplete="off" disabled={busy}/></label>}{children}</>}
    {error&&<div className="action-review__error" role="alert"><strong>{action.label} was not confirmed</strong><p>{error}</p><p>The original target above remains selected. {phase==='unconfirmed'?'Resolve the reported requirement, then refresh the retained server state before requesting this action again.':'Retry reuses the same submission reference.'}</p></div>}
    {onResolve&&(blockedReason||error)&&phase!=='accepted'&&<button type="button" disabled={busy} onClick={onResolve}>{resolveLabel||'Review requirements'}</button>}
    {busy&&<p role="status">Submitting {action.label.toLowerCase()} for the exact target above…</p>}
    {phase==='accepted'&&<section className="action-review__receipt" role="status"><h3>{result.label||'Request accepted'}</h3><p>{result.message||'Check the retained workflow state for its outcome.'}</p>{result.runId&&<dl><dt>Resulting run ID</dt><dd>{result.runId}</dd></dl>}{result.href&&<a href={result.href}>Open resulting run</a>}</section>}
   </div>
   <footer><button type="button" onClick={onClose} disabled={busy}>{phase==='accepted'?'Done':'Cancel'}</button>{phase!=='accepted'&&phase!=='unconfirmed'&&<button type="button" className="action-review__confirm" onClick={submit} disabled={busy||Boolean(blockedReason)||(onApproverChange&&!String(approver||'').trim())}>{busy?'Submitting…':`Confirm ${action.label.toLowerCase()}`}</button>}</footer>
  </section>
 </div>,document.body);
}
