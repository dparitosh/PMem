import React,{useEffect,useRef,useState} from 'react';
import {dataPipelineAPI as api} from '../services/apiClient';
import {getCredentialProfile} from '../services/serviceAuth';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import {confirmedSubmissionRejection} from '../services/workflowSubmission';
import './XmlAnalyticsLoader.css';
import RdfSourceUpload from './RdfSourceUpload';
import BusinessAnalyticsModel from './BusinessAnalyticsModel';

const KEY='depo-semantic-data-task';
const events=['depo:session-replaced','depo:session-expired','depo:credentials-cleared','depo:credentials-changed'];
const short=iri=>String(iri).split(/[#/:]/).filter(Boolean).pop()||iri;
function retained(){try{return JSON.parse(sessionStorage.getItem(KEY))||null;}catch{return null;}}

export default function SemanticDataWorkbench(){
  const [sources,setSources]=useState(null),[datasets,setDatasets]=useState(null),[jobs,setJobs]=useState([]);
  const [sourceOffset,setSourceOffset]=useState(0),[sourceNext,setSourceNext]=useState(null),[datasetOffset,setDatasetOffset]=useState(0),[datasetNext,setDatasetNext]=useState(null);
  const [source,setSource]=useState(''),[dataset,setDataset]=useState(''),[model,setModel]=useState(null);
  const [assessment,setAssessment]=useState(null);
  const [businessModel,setBusinessModel]=useState({});
  const [classId,setClassId]=useState(''),[prefix,setPrefix]=useState(''),[fields,setFields]=useState([]),[properties,setProperties]=useState([]);
  const [algorithm,setAlgorithm]=useState('profile'),[actor,setActor]=useState(''),[jobChoice,setJobChoice]=useState('');
  const [revision,setRevision]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState(''),[loadErrors,setLoadErrors]=useState({});
  const [pending,setPending]=useState(retained),[checked,setChecked]=useState(false);
  const mounted=useRef(true);
  const generation=useRef(0),selection=useRef(0),locked=useRef(false),details=useRef(null);
  function retain(value){if(mounted.current)setPending(value);try{if(value)sessionStorage.setItem(KEY,JSON.stringify(value));else sessionStorage.removeItem(KEY);}catch{/* The in-memory guard remains active. */}}
  useEffect(()=>{
    mounted.current=true;
    const reset=()=>{generation.current++;selection.current++;details.current?.abort();setAssessment(null);setBusinessModel({});setModel(null);setFields([]);setProperties([]);setSource('');setDataset('');setClassId('');setActor('');setJobs([]);setRevision(value=>value+1);};
    events.forEach(event=>window.addEventListener(event,reset));
    return()=>{mounted.current=false;events.forEach(event=>window.removeEventListener(event,reset));generation.current++;selection.current++;details.current?.abort();};
  },[]);
  useEffect(()=>{
    const controller=new AbortController(),current=generation.current;
    const valid=()=>!controller.signal.aborted&&current===generation.current;
    setSources(null);setDatasets(null);setLoadErrors({});
    const options={signal:controller.signal,timeout:15000};
    const read=(key,call,apply)=>Promise.resolve().then(call).then(response=>{if(valid())apply(response.data);}).catch(failure=>{if(valid())setLoadErrors(old=>({...old,[key]:apiErrorMessage(failure,`${key} is unavailable. This does not establish that no records exist.`)}));});
    read('Catalog and registry',()=>api.semanticSources(sourceOffset,options),data=>{if(!Array.isArray(data.sources))throw new Error('Invalid registered-source response');setSources(data.sources);setSourceNext(data.next_offset);});
    read('Semantic datasets',()=>api.semanticDatasets(datasetOffset,options),data=>{if(!Array.isArray(data.datasets))throw new Error('Invalid semantic dataset response');setDatasets(data.datasets);setDatasetNext(data.next_offset);});
    read('Processing workflows',()=>api.definitions(),data=>{if(!Array.isArray(data.definitions))throw new Error('Invalid process response');setJobs(data.definitions);});
    const token=getCredentialProfile('DATA_JOB_EXECUTION_TOKEN');
    if(token)read('Execution access',()=>api.executionIdentity(token,options),data=>setActor(data.actor||''));
    return()=>controller.abort();
  },[revision,sourceOffset,datasetOffset]);
  async function chooseDataset(id){
    details.current?.abort();const controller=new AbortController();details.current=controller;const current=++selection.current;
    setDataset(id);setBusinessModel({});setAssessment(null);setModel(null);setClassId('');setFields([]);setProperties([]);setError('');setPrefix('');
    if(!id)return;
    try{const response=await api.semanticSchema(id,{signal:controller.signal,timeout:15000});if(!controller.signal.aborted&&current===selection.current){if(response.data?.dataset?.dataset_id!==id)throw new Error('Dataset identity mismatch');setModel(response.data);}
      const assessed=await api.semanticChangeAssessment(id,{signal:controller.signal,timeout:15000});if(!controller.signal.aborted&&current===selection.current)setAssessment(assessed.data);}
    catch(failure){if(!controller.signal.aborted&&current===selection.current)setError(apiErrorMessage(failure,'Dataset details could not be loaded.'));}
  }
  async function chooseClass(id){
    details.current?.abort();const controller=new AbortController();details.current=controller;const current=++selection.current;
    setClassId(id);setProperties([]);setFields([]);setError('');if(!id)return;
    try{const response=await api.semanticFields(dataset,id,{signal:controller.signal,timeout:15000});if(!controller.signal.aborted&&current===selection.current){if(response.data?.dataset_id!==dataset||response.data?.class_iri!==id)throw new Error('Entity scope mismatch');setFields(response.data.rows||[]);}}
    catch(failure){if(!controller.signal.aborted&&current===selection.current)setError(apiErrorMessage(failure,'Fields could not be loaded.'));}
  }
  const selectedSource=(sources||[]).find(item=>`${item.source_id}|${item.artifact_id}`===source);
  const type=dataset?(algorithm==='source-review'?'semantic-source-review':'semantic-dataset-analysis'):'rdf-semantic-materialize';
  const processes=jobs.filter(job=>job.job_type===type&&job.lifecycle_state==='approved'&&job.enabled);
  const selectedJob=processes.length===1?processes[0]:processes.find(job=>`${job.job_id}:${job.version}`===jobChoice);
  async function createDraft(){
    if(locked.current)return;
    const token=getCredentialProfile('DATA_JOB_APPROVAL_TOKEN');
    if(!token){setError('Connect workflow-authoring access in Admin before preparing a processing definition.');return;}
    const current=generation.current;
    locked.current=true;setBusy(true);setError('');
    try{
      await api.createDefinition({job_id:type,version:'1.0.0',name:dataset?(algorithm==='source-review'?'Semantic source change assessment':'Semantic dataset analysis'):'RDF semantic preparation',job_type:type,quality_profile:'semantic-core-v1',enabled:true},token);
      if(current===generation.current){setError('Draft created. Review and approve this workflow in Data Flow before running it.');setRevision(value=>value+1);}
    }catch(failure){if(current===generation.current)setError(apiErrorMessage(failure,'Inspect workflow definitions in Data Flow before retrying creation.'));}
    finally{locked.current=false;if(mounted.current)setBusy(false);}
  }
  async function submit(){
    if(locked.current||pending)return;
    setError('');const token=getCredentialProfile('DATA_JOB_EXECUTION_TOKEN');
    if(!actor||!token||!selectedJob){setError('Connect execution access and select an approved processing workflow.');return;}
    if(!dataset&&!selectedSource){setError('Choose a catalog or registry source.');return;}
    if(dataset&&!['source-review','business-overview'].includes(algorithm)&&!classId){setError('Choose business records to analyse.');return;}
    if(dataset&&((['frequency','numeric-summary'].includes(algorithm)&&properties.length!==1)||(algorithm==='correlation'&&properties.length!==2)||(algorithm==='dimension-preview'&&!properties.length))){setError('Select one property for grouping or numeric measures, two for comparison, or at least one dimension attribute.');return;}
    if(dataset&&algorithm==='business-overview'&&(!businessModel.product_class||!businessModel.part_class)){setError('Select portfolio product and part record types for this model.');return;}
    const payload=dataset?{...(algorithm==='source-review'?{dataset_id:dataset}:{dataset_id:dataset,...(algorithm==='business-overview'?{business_model:businessModel}:{class_iri:classId,property_iris:properties}),algorithm}),...(model?.dataset?.configuration_id?{configuration_id:model.dataset.configuration_id}:{})}:{source_id:selectedSource.source_id,artifact_id:selectedSource.artifact_id};
    const current=generation.current;
    locked.current=true;setBusy(true);retain({unknown:true,job:selectedJob.name});
    try{
      const response=await api.runDefinition(selectedJob.job_id,selectedJob.version,payload,{approved_by:actor,approval_token:token});
      const id=response.data?.run_manifest?.run_id||response.data?.run?.run_id;
      if(!id)throw new Error('Submission response did not identify a retained run');
      retain({run_id:id,job:selectedJob.name,...(current!==generation.current?{previousConnection:true}:{})});
    }catch(failure){const id=failure.response?.headers?.['x-depo-run-id'];if(id)retain({run_id:id,job:selectedJob.name,...(current!==generation.current?{previousConnection:true}:{})});else if(confirmedSubmissionRejection(failure))retain(null);if(mounted.current&&current===generation.current)setError(apiErrorMessage(failure,'The submission outcome is unknown. Inspect Data Flow before retrying.'));}
    finally{locked.current=false;if(mounted.current)setBusy(false);}
  }
  const namespaces=Array.from(new Map((model?.namespaces||[]).filter(item=>item.namespace_uri&&(model?.classes||[]).some(entity=>entity.iri.slice(0,Math.max(entity.iri.lastIndexOf('#'),entity.iri.lastIndexOf('/'),entity.iri.lastIndexOf(':'))+1)===item.namespace_uri)).map(item=>[item.namespace_uri,item])).values());
  const classes=(model?.classes||[]).filter(item=>!prefix||item.iri.startsWith(prefix));
  return <section className="xml-analytics-loader" aria-label="Catalog driven analytics">
    <header><h3>Build reports from registered business data</h3><p>Choose data from the Data Catalog or Metadata Registry. Reuse its vocabulary, records and source version; XSD is not required.</p><button disabled={busy} onClick={()=>{generation.current++;selection.current++;details.current?.abort();setModel(null);setDataset('');setClassId('');setFields([]);setProperties([]);setRevision(value=>value+1);}}>Refresh registered data</button></header>
    <RdfSourceUpload onRegistered={()=>{setSourceOffset(0);setRevision(value=>value+1);}}/>
    {Object.entries(loadErrors).map(([key,message])=><p role="alert" key={key}>{message}</p>)}
    <div className="analytics-form-row"><label>Registered source<select value={source} disabled={busy||!!pending} onChange={event=>{setSource(event.target.value);setJobChoice('');chooseDataset('');}}><option value="">Choose from Catalog or Registry</option>{(sources||[]).map(item=><option key={`${item.source_id}|${item.artifact_id}`} value={`${item.source_id}|${item.artifact_id}`}>{item.name} · {item.version||item.status} · {item.filename||item.origin}</option>)}</select></label><span>Sources keep their owner, version and lineage.</span></div>
    {sources?.length===0&&<p>No retained RDF references are registered on this page. <a href="#/catalog">Browse Data Catalog</a> or <a href="#/registry">register an RDF source</a>. Live graph data needs a registered snapshot before reproducible analysis.</p>}
    {selectedSource&&<p>Namespace: {selectedSource.namespace_uri||'Read from the RDF source'} · Owner: {selectedSource.owner||'Not recorded'}</p>}
    {(sourceNext!=null||sourceOffset>0)&&<p><button disabled={!sourceOffset} onClick={()=>setSourceOffset(Math.max(0,sourceOffset-50))}>Previous sources</button><button disabled={sourceNext==null} onClick={()=>setSourceOffset(sourceNext)}>More sources</button></p>}
    <div className="analytics-form-row"><label>Prepared semantic dataset<select value={dataset} disabled={busy||!!pending} onChange={event=>{setSource('');setJobChoice('');chooseDataset(event.target.value);}}><option value="">Choose existing records to analyse</option>{(datasets||[]).map(item=><option value={item.dataset_id} key={item.dataset_id}>{item.name} · source {item.source_version?.version||'version not recorded'} · snapshot {item.dataset_id.slice(0,8)} · {item.counts?.entities??0} typed records · {item.projection_version}</option>)}</select></label><span>Prepared records remain separate from approved published products.</span></div>
    {datasets?.length===0&&<p>No semantic snapshots have been prepared yet. Choose a registered RDF source, then run its approved preparation workflow.</p>}
    {(datasetNext!=null||datasetOffset>0)&&<p><button disabled={!datasetOffset} onClick={()=>setDatasetOffset(Math.max(0,datasetOffset-50))}>Previous datasets</button><button disabled={datasetNext==null} onClick={()=>setDatasetOffset(datasetNext)}>More datasets</button></p>}
    {model&&<>{model.dataset.configuration_id&&<p>Input baseline retained. New source versions do not replace this snapshot automatically.</p>}<p role="status">Source change assessment: {String(assessment?.status||'not_assessed').replaceAll('_',' ')}{assessment?.assessed_at?` · ${assessment.assessed_at}`:''}. Published results are retained.</p><label>Vocabulary / namespace<select value={prefix} onChange={event=>{selection.current++;details.current?.abort();setPrefix(event.target.value);setClassId('');setProperties([]);setFields([]);}}><option value="">All vocabularies</option>{namespaces.map(item=><option key={`${item.namespace_uri}|${item.prefix}`} value={item.namespace_uri}>{item.prefix||'Unprefixed'} · {item.namespace_uri}</option>)}</select></label><label>Business records<select value={classId} onChange={event=>chooseClass(event.target.value)}><option value="">Choose an entity type</option>{classes.map(item=><option key={item.iri} value={item.iri}>{item.name} · {item.entities} records</option>)}</select></label>
      {!model.classes.length&&<p>This snapshot contains vocabulary but no explicitly typed business instances. Definitions alone cannot establish a business KPI.</p>}
      <label>Analysis<select value={algorithm} onChange={event=>{setAlgorithm(event.target.value);setProperties([]);}}><option value="business-overview">Product portfolio, classification, traceability and manufacturing</option><option value="source-review">Check source changes and refresh needs</option><option value="profile">Data completeness and numeric coverage</option><option value="frequency">Group records by a property</option><option value="numeric-summary">Numeric measures: average, range and variation</option><option value="correlation">Compare two numeric properties</option><option value="dimension-preview">Preview dimension attributes</option></select></label>
      {!['profile','source-review','business-overview'].includes(algorithm)&&<fieldset><legend>Select properties</legend>{fields.map(field=><label key={field.property_iri}><input type="checkbox" checked={properties.includes(field.property_iri)} onChange={()=>setProperties(old=>old.includes(field.property_iri)?old.filter(value=>value!==field.property_iri):[...old,field.property_iri])}/>{field.label||short(field.property_iri)} · {field.entities_with_value} records with a value{field.numeric_values?' · numeric values available':''}</label>)}</fieldset>}
      {algorithm==='business-overview'&&<BusinessAnalyticsModel datasetId={dataset} classes={model.classes} value={businessModel} onChange={setBusinessModel}/>}
      <p>No unit conversion or identity merging is assumed. Repeated/non-numeric values require review before numeric analysis. Dimension output is a bounded preview.</p></>}
    <div className="analytics-form-row"><label>Approved processing workflow<select value={selectedJob?`${selectedJob.job_id}:${selectedJob.version}`:jobChoice} disabled={busy||!!pending} onChange={event=>setJobChoice(event.target.value)}><option value="">Choose an approved workflow</option>{processes.map(job=><option key={`${job.job_id}:${job.version}`} value={`${job.job_id}:${job.version}`}>{job.name} · {job.version}</option>)}</select></label><span>{actor?`Connected requester: ${actor}`:'Connect execution access in Admin.'}</span></div>
    {!processes.length&&<p>A steward must configure and approve a <strong>{dataset?(algorithm==='source-review'?'Semantic source change assessment':'Semantic dataset analysis'):'RDF semantic preparation'}</strong> workflow. <a href="#/data-flow">Review processing workflows</a>. This screen never grants its own approval. {!jobs.some(job=>job.job_type===type)&&<button disabled={busy} onClick={createDraft}>Prepare workflow draft for review</button>}</p>}
    <button disabled={busy||!!pending||!selectedJob||!actor||(!dataset&&!source)} onClick={submit}>{dataset?(algorithm==='source-review'?'Check source changes with worker':'Run analysis with worker'):'Prepare semantic records with worker'}</button>
    {error&&<p role="alert">{error}</p>}{pending&&<section aria-label="Retained semantic processing">{pending.previousConnection&&<p>This request belongs to the previous connection. Revalidate its retained result with your current access.</p>}<p>{pending.run_id?'Processing request retained. Inspect its result before creating another request.':'Submission outcome is unconfirmed. Inspect Data Flow history before retrying.'}</p><a href={pending.run_id?`#/data-flow?run_id=${encodeURIComponent(pending.run_id)}`:'#/data-flow'}>Open Data Flow result and publication review</a><label><input type="checkbox" checked={checked} onChange={event=>setChecked(event.target.checked)}/>I checked the retained result or confirmed that no request was created</label><button disabled={!checked||busy} onClick={()=>{retain(null);setChecked(false);setRevision(value=>value+1);}}>Prepare another request</button></section>}
    <details><summary>How the records are organised</summary><p>Versioned master records retain entity IRIs, property IRIs, namespace aliases, literal values, datatypes, languages and source provenance. Units remain explicit source metadata. Different namespaces or repeated values are never silently combined.</p><p>Supported now: completeness, frequency distributions, descriptive numeric statistics, Pearson correlation and dimension previews. Arbitrary code execution, automatic causal claims and automatic business approval are not supported.</p></details>
  </section>;
}
