import React,{useEffect,useRef,useState} from 'react';
import {metadataRegistryAPI} from '../services/apiClient';
import {getCredentialProfile} from '../services/serviceAuth';
import {apiErrorMessage} from '../utils/apiErrorMessage';

export default function RdfSourceUpload({onRegistered}){
 const [name,setName]=useState(''),[file,setFile]=useState(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 const locked=useRef(false),generation=useRef(0),mounted=useRef(true);
 useEffect(()=>{mounted.current=true;const reset=()=>{generation.current++;setMessage('Access changed. Refresh registered data before retrying this upload.');};
 const events=['depo:session-replaced','depo:session-expired','depo:credentials-cleared','depo:credentials-changed'];events.forEach(e=>window.addEventListener(e,reset));
 return()=>{mounted.current=false;generation.current++;events.forEach(e=>window.removeEventListener(e,reset));};},[]);
 async function upload(event){event.preventDefault();if(locked.current)return;
 const token=getCredentialProfile('ONTOLOGY_APPROVAL_TOKEN');if(!token){setMessage('Connect metadata-authoring access in Admin before registering a source.');return;}
 if(!file||!name.trim()){setMessage('Choose an RDF file and enter its business name.');return;}
 if(file.size>25*1024*1024){setMessage('Choose a file no larger than 25 MiB.');return;}
 const current=generation.current;locked.current=true;setBusy(true);setMessage('');
 try{const {data}=await metadataRegistryAPI.registerRdfSource(file,name.trim(),token);
 if(mounted.current&&current===generation.current){setMessage(`Registered ${data.asset.name}. Select it in Registered source, then prepare records with an approved workflow. Registration does not approve publication.`);onRegistered?.(data);}}
 catch(error){if(mounted.current&&current===generation.current)setMessage(apiErrorMessage(error,'Registration outcome is unknown. Refresh the Metadata Registry before retrying; the same name and file reuse the retained registration.'));}
 finally{locked.current=false;if(mounted.current)setBusy(false);}}
 return <details><summary>Add a data source from an RDF file</summary><form onSubmit={upload}>
 <p>Upload business records in Turtle, N-Triples, RDF/XML or inline-context JSON-LD. The app retains the file and registers its metadata; no artifact ID is needed. This creates a draft, not an approved release.</p>
 <div className="analytics-form-row"><label>Source name<input value={name} disabled={busy} maxLength={300} onChange={e=>setName(e.target.value)}/></label>
 <label>RDF source file<input type="file" accept=".ttl,.nt,.rdf,.owl,.jsonld" disabled={busy} onChange={e=>setFile(e.target.files?.[0]||null)}/></label></div>
 <button type="submit" disabled={busy||!file||!name.trim()}>{busy?'Registering source…':'Register source draft'}</button>
 {message&&<p role="status">{message}</p>}<a href="#/registry">Open Metadata Registry</a>
 </form></details>;
}
