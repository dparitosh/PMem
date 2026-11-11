import React,{useEffect,useState} from 'react';
import {dataPipelineAPI as api} from '../services/apiClient';
import {apiErrorMessage} from '../utils/apiErrorMessage';
const roles=[['product','Portfolio product record type'],['part','Part / revision record type'],['requirement','Requirement record type'],['process','Manufacturing process record type']];
const label=iri=>String(iri).split(/[#/:]/).filter(Boolean).pop()||iri;
export default function BusinessAnalyticsModel({datasetId,classes,value,onChange}){
 const [panel,setPanel]=useState('records');
 const [fields,setFields]=useState({}),[errors,setErrors]=useState({});
 useEffect(()=>{const controller=new AbortController();setFields({});setErrors({});
 roles.forEach(([role])=>{const iri=value[role+'_class'];if(!iri)return;
 api.semanticFields(datasetId,iri,{signal:controller.signal,timeout:15000}).then(({data})=>{
 if(!controller.signal.aborted){if(data.dataset_id!==datasetId||data.class_iri!==iri)throw new Error('Field scope mismatch');setFields(old=>({...old,[role]:data.rows||[]}));}
 }).catch(error=>{if(!controller.signal.aborted)setErrors(old=>({...old,[role]:apiErrorMessage(error,'Fields unavailable; refresh this selection.')}));});});
 return()=>controller.abort();
 },[datasetId,value.product_class,value.part_class,value.requirement_class,value.process_class]);
 function choose(role,iri){const next={...value};if(iri)next[role+'_class']=iri;else delete next[role+'_class'];
 for(const key of ['product_part_property','requirement_property','bom_property','process_property','classification_properties'])delete next[key];onChange(next);}
 function property(key,v){const next={...value};if(v)next[key]=v;else delete next[key];onChange(next);}
 return <section aria-label="Business analytics model"><h4>Portfolio → parts → engineering → manufacturing</h4>
 <p>Select what each source record means. Relationships below are outgoing from the named source type. Counts keep distinct source identities; this draft model does not approve a change or certify completeness.</p>
 <nav className="semantic-model-tabs" aria-label="Business model sections">{[['records','Record types'],['links','Relationships'],['dimensions','Dimensions']].map(([id,title])=><button type="button" key={id} aria-pressed={panel===id} onClick={()=>setPanel(id)}>{title}</button>)}</nav>
 <div hidden={panel!=='records'}><div className="analytics-form-row">{roles.map(([role,title])=><label key={role}>{title}<select value={value[role+'_class']||''} onChange={e=>choose(role,e.target.value)}><option value="">{['product','part'].includes(role)?'Choose a record type':'Not assessed'}</option>{classes.map(c=><option key={c.iri} value={c.iri}>{c.name} · {c.entities} records</option>)}</select>{errors[role]&&<span role="alert">{errors[role]}</span>}</label>)}</div>
 </div><div hidden={panel!=='links'}><div className="analytics-form-row">{[['product_part_property','product','Product → part relationship'],['requirement_property','part','Part → requirement relationship'],['bom_property','part','Parent part → child part relationship'],['process_property','part','Part → manufacturing process relationship']].map(([key,role,title])=><label key={key}>{title}<select value={value[key]||''} disabled={!fields[role]} onChange={e=>property(key,e.target.value)}><option value="">Not assessed</option>{(fields[role]||[]).map(f=><option key={f.property_iri} value={f.property_iri}>{f.label||label(f.property_iri)}</option>)}</select></label>)}</div>
 </div><div hidden={panel!=='dimensions'}><fieldset><legend>Part classification dimensions — up to six</legend>{(fields.part||[]).map(f=><label key={f.property_iri}><input type="checkbox" checked={(value.classification_properties||[]).includes(f.property_iri)} disabled={(value.classification_properties||[]).length>=6&&!(value.classification_properties||[]).includes(f.property_iri)} onChange={()=>{const old=value.classification_properties||[];onChange({...value,classification_properties:old.includes(f.property_iri)?old.filter(p=>p!==f.property_iri):[...old,f.property_iri]});}}/>{f.label||label(f.property_iri)}</label>)}</fieldset>
 <p>Requirement coverage means recorded part links / selected requirements. Process coverage means parts with recorded process links / selected parts. BOM completeness stays unassessed without expected assembly scope, revisions and effectivity. Counts do not establish satisfaction, manufacturability or unit-normalized quantities.</p>
 </div></section>;
}
