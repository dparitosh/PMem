import React,{useState} from 'react';
import {downloadArtifact} from '../services/artifactDownload';
import {buildSemanticServiceUrl} from '../config';
import {apiErrorMessage} from '../utils/apiErrorMessage';
const display = value => value == null || value === '' ? 'Not recorded' : typeof value === 'object' ? JSON.stringify(value) : String(value);
export default function ProductEvidenceDetails({detail,catalog=false}) {
  const [downloading,setDownloading]=useState(''),[error,setError]=useState('');
  async function download(record){
    const id=record.product_id||detail.product_id,version=record.version;if(!id||!version||downloading)return;
    setDownloading(version);setError('');
    try{await downloadArtifact(buildSemanticServiceUrl('dataProducts',`/api/v1/data-products/${encodeURIComponent(id+':'+version)}/download`),`${id}-${version}.zip`);}
    catch(failure){setError(apiErrorMessage(failure,'Package download failed.'));}finally{setDownloading('');}
  }
  const versions=Array.isArray(detail.versions)?detail.versions:[detail];
  return <section aria-label="Product evidence and delivery">
    <h3>{detail.name || detail.versions?.[0]?.name || detail.product_id || 'Selected product'}</h3>{error&&<p role="alert">{error}</p>}
    {versions.map((record,index)=><article key={record.version || index} className="product-evidence-card">
      <dl>{['version','domain','owner','steward','classification','lifecycle_state','status','product_kind','analytics_readiness','quality_status'].map(key=><React.Fragment key={key}><dt>{catalog&&key==='status'?'Catalog presence':key.replaceAll('_',' ')}</dt><dd>{catalog&&key==='status'?'Registered':display(record[key] ?? detail[key])}</dd></React.Fragment>)}</dl>
      {record.version&&(['published','pending_catalog_registration'].includes(record.status)||(catalog&&record.lifecycle_state==='published'))&&<button type="button" disabled={!!downloading} onClick={()=>download(record)}>Download package {record.version}</button>}
      <p>{Array.isArray(record.sources)&&`Sources: ${record.sources.length}`}{Array.isArray(record.artifacts)&&` / Artifacts: ${record.artifacts.length}`}{Array.isArray(record.semantic_releases)&&` / Semantic releases: ${record.semantic_releases.length}`}</p>
      {record.status==='pending_catalog_registration' && <p role="status">Package retained; catalog delivery needs attention. Review the delivery evidence before retrying publication.</p>}
      {(record.sources||[]).filter(source=>source.consumption?.schema).map((source,i)=><section key={i} aria-label="Analytics consumption"><h4>Analytics ready for consumption</h4><p>Operational data store: {source.consumption.schema}. Readiness: {source.consumption.analytics_readiness}</p><ul>{(source.consumption.business_views||[]).map(view=><li key={view.view}>{view.name} · {view.kind} · {source.consumption.schema}.{view.view}{view.unit?` · Unit: ${view.unit}`:''}{view.description?` · ${view.description}`:''}</li>)}</ul><p>Database access must be provisioned separately for the consumer.</p></section>)}
      {(record.sources || []).length>0 && <details><summary>Source provenance</summary><ul>{record.sources.map((source,i)=><li key={i}>{source.name||source.source_name||source.filename||source.schema||source.source_kind||'Retained source'}{' '}{source.run_id&&<a href={`#/data-flow?run_id=${encodeURIComponent(source.run_id)}`}>View source run</a>}{source.ontology_id&&<a href={`#/ontology?target=${encodeURIComponent(source.ontology_id)}`}>View source ontology</a>}</li>)}</ul></details>}
    </article>)}
  </section>;
}
