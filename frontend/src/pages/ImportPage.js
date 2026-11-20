import React,{useEffect,useState} from 'react';
import ImportWorkspace from '../features/import/ImportWorkspace';
import './ImportPage.css';

export default function ImportPage(){
 const [hash,setHash]=useState(()=>window.location.hash);
 useEffect(()=>{const update=()=>setHash(window.location.hash);window.addEventListener('hashchange',update);window.addEventListener('popstate',update);return()=>{window.removeEventListener('hashchange',update);window.removeEventListener('popstate',update);};},[]);
 const params=new URLSearchParams(hash.split('?')[1]||'');
 const requested=params.get('workflow');
 const initialWorkflow=['instance.import','ontology.create','document.unstructured'].includes(requested)?requested:['qif','sysml'].includes(params.get('view'))?'ontology.create':null;
 return <div className="depo-page"><ImportWorkspace initialWorkflow={initialWorkflow}/></div>;
}
