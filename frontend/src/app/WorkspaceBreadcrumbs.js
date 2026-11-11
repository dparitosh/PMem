import React, {useEffect,useState} from 'react';
const views={analytics:'Available analytics',prepare:'Prepare data',library:'Product portfolio',create:'Create & review',governance:'Governance',sources:'Ingested sources',runs:'Runs',definitions:'Definitions',alignment:'Semantic Bridge',structural:'Create & review',pipeline:'Create & review'};
const steps=['Choose data','Configure analysis','Review workflow'];
export default function WorkspaceBreadcrumbs({page,label}) {
 const [hash,setHash]=useState(()=>window.location.hash);
 useEffect(()=>{const update=()=>setHash(window.location.hash);window.addEventListener('hashchange',update);window.addEventListener('popstate',update);return()=>{window.removeEventListener('hashchange',update);window.removeEventListener('popstate',update);};},[]);
 const params=new URLSearchParams(hash.split('?')[1]||'');
 const view=views[params.get('view')];
 const step=Number(params.get('analytics_step'));
 const stepLabel=['data-products','catalog'].includes(page)&&params.get('view')==='analytics'&&params.has('analytics_step')&&Number.isInteger(step)&&step>=0&&step<3?steps[step]:null;
 const detail=params.has('run_id')?'Run details':stepLabel||view;
 return <div className="workspace-navigation"><nav aria-label="Breadcrumb"><ol>
 <li>{page==='home'?<span aria-current="page">Home</span>:<a href="#/home">Home</a>}</li>
 {page!=='home'&&<li>{detail?<a href={`#/${page}`}>{label}</a>:<span aria-current="page">{label}</span>}</li>}
 {detail&&<li><span aria-current="page">{detail}</span></li>}
 </ol></nav><div className="workspace-history"><button type="button" aria-label="Go back" onClick={()=>window.history.back()}>← Back</button><button type="button" aria-label="Go forward" onClick={()=>window.history.forward()}>Forward →</button></div></div>;
}
