import React, {useId,useRef} from 'react';
import './DataWorkspace.css';

export function DataJourney({current}) {
  const steps=[['import','Import sources','Bring in files and link meaning','#/import'],['flow','Process & validate','Run pipelines and inspect evidence','#/data-flow'],['products','Build products','Review, approve and package','#/data-products'],['catalog','Discover & reuse','Find sources and governed products','#/catalog']];
  return <nav className="data-journey" aria-label="Data lifecycle workflow">{steps.map(([key,title,hint,url],index)=><a key={key} href={url} aria-current={current===key?'step':undefined}><span className="data-journey__number">{index+1}</span><span><strong>{title}</strong><small>{hint}</small></span></a>)}</nav>;
}

export default function DataWorkspace({label,tabs,active,onChange,children}) {
 const id=useId(),refs=useRef([]);
 const navigate=(event,index)=>{
  const next=event.key==='Home'?0:event.key==='End'?tabs.length-1:event.key==='ArrowRight'?(index+1)%tabs.length:event.key==='ArrowLeft'?(index+tabs.length-1)%tabs.length:null;
  if(next===null)return;
  event.preventDefault();onChange(tabs[next].id);refs.current[next]?.focus();
 };
 return <div className="data-workspace">
  <div className="data-workspace__tabs" role="tablist" aria-label={label}>{tabs.map((tab,index)=><button key={tab.id} type="button" role="tab" id={`${id}-tab-${tab.id}`} aria-controls={`${id}-panel-${tab.id}`} aria-selected={active===tab.id} tabIndex={active===tab.id?0:-1} ref={node=>{refs.current[index]=node;}} onClick={()=>onChange(tab.id)} onKeyDown={event=>navigate(event,index)}>{tab.label}</button>)}</div>
  {tabs.map(tab=><section key={tab.id} className="data-workspace__panel" role="tabpanel" id={`${id}-panel-${tab.id}`} aria-labelledby={`${id}-tab-${tab.id}`} hidden={active!==tab.id} tabIndex={0}>{children[tab.id]}</section>)}
 </div>;
}
