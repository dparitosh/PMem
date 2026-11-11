import React, {useId,useRef,useState} from 'react';

export default function EvidenceProductOptions({catalog=false,rows=[],loading=false,error='',draftCount=null,onStructural,onPipeline}) {
  const id=useId();
  const tabs=useRef([]);
  const [active,setActive]=useState(()=>new URLSearchParams(window.location.hash.split('?')[1]||'').get('view')==='pipeline'?1:0);
  const names=['Structural analytics','Pipeline evidence'];
  const navigate=(event,index)=>{
    const next=event.key==='Home'?0:event.key==='End'?1:event.key==='ArrowRight'?(index+1)%2:event.key==='ArrowLeft'?(index+1)%2:null;
    if(next===null)return;
    event.preventDefault();setActive(next);tabs.current[next]?.focus();
  };
  const count=kind=>loading?'Checking…':error?'Unavailable':rows.filter(row=>row.product_kind===kind).length;
  const label=catalog?'Cataloged versions (loaded)':'Retained packages (loaded)';
  return <section aria-label="Evidence products you can build" className="evidence-product-options">
    <h3>Evidence products you can build</h3>
    <div role="tablist" aria-label="Evidence product workflows" className="evidence-product-options__tabs">
      {names.map((name,index)=><button key={name} type="button" role="tab" id={`${id}-tab-${index}`} aria-controls={`${id}-panel-${index}`} aria-selected={active===index} tabIndex={active===index?0:-1} ref={node=>{tabs.current[index]=node;}} onClick={()=>setActive(index)} onKeyDown={event=>navigate(event,index)}>{name}</button>)}
    </div>
    <div role="tabpanel" id={`${id}-panel-0`} aria-labelledby={`${id}-tab-0`} hidden={active!==0} tabIndex={0}>
      <article>
        <h4>Structural analytics</h4>
        <p>A reviewable schema plan: entity tables, keys, relationships and generated SQL from an imported schema. Business dimensions and KPIs need their own definitions and approval.</p>
        <dl><dt>Schema drafts available</dt><dd>{draftCount===null?'Not verified':draftCount}</dd><dt>{label}</dt><dd>{count('schema-design-evidence')}</dd></dl>
        {catalog?<a href="#/data-products?view=structural">Review structural analytics</a>:<button type="button" className="depo-button" onClick={onStructural}>Review structural analytics</button>}
      </article>
    </div>
    <div role="tabpanel" id={`${id}-panel-1`} aria-labelledby={`${id}-tab-1`} hidden={active!==1} tabIndex={0}>
      <article>
        <h4>Pipeline evidence</h4>
        <p>Validation reports, quality measurements and other retained outputs from completed Data Flow runs, packaged with source references and provenance.</p>
        <dl><dt>Evidence source</dt><dd>Completed runs with retained artifacts</dd><dt>{label}</dt><dd>{count('pipeline-evidence')}</dd></dl>
        {catalog?<a href="#/data-products?view=pipeline">Review pipeline evidence</a>:<button type="button" className="depo-button" onClick={onPipeline}>Review pipeline evidence</button>}
        {' · '}<a href="#/data-flow">Open Data Flow runs</a>
      </article>
    </div>
    <p>These are available creation workflows. Counts above describe retained records; creating a draft is separate from approving and publishing a product.</p>
  </section>;
}
