import React from 'react';
const display = value => value == null || value === '' ? 'Not recorded' : typeof value === 'object' ? JSON.stringify(value) : String(value);
export default function ProductEvidenceDetails({detail}) {
  const versions=Array.isArray(detail.versions)?detail.versions:[detail];
  return <section aria-label="Product evidence and delivery">
    <h3>{detail.name || detail.product_id || 'Selected product'}</h3>
    {versions.map((record,index)=><article key={record.version || index} className="product-evidence-card">
      <dl>{['version','domain','owner','steward','classification','lifecycle_state','status','product_kind','analytics_readiness','quality_status'].map(key=><React.Fragment key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{display(record[key] ?? detail[key])}</dd></React.Fragment>)}</dl>
      <p>Sources: {record.sources?.length ?? 'Not recorded'} · Artifacts: {record.artifacts?.length ?? 'Not recorded'} · Semantic releases: {record.semantic_releases?.length ?? 'Not recorded'}</p>
      {record.status==='pending_catalog_registration' && <p role="status">Package retained; catalog delivery needs attention. Review the delivery evidence before retrying publication.</p>}
      {(record.sources||[]).filter(source=>source.consumption?.schema).map((source,i)=><section key={i} aria-label="Analytics consumption"><h4>Analytics ready for consumption</h4><p>Operational data store: {source.consumption.schema}. Readiness: {source.consumption.analytics_readiness}</p><ul>{(source.consumption.business_views||[]).map(view=><li key={view.view}>{view.name} · {view.kind} · {source.consumption.schema}.{view.view}{view.unit?` · Unit: ${view.unit}`:''}{view.description?` · ${view.description}`:''}</li>)}</ul><p>Database access must be provisioned separately for the consumer.</p></section>)}
      {(record.sources || []).length>0 && <details><summary>Source provenance</summary><ul>{record.sources.map((source,i)=><li key={i}>{display(source)}</li>)}</ul></details>}
    </article>)}
    <details><summary>Technical record</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:350,overflow:'auto'}}>{JSON.stringify(detail,null,2)}</pre></details>
  </section>;
}
