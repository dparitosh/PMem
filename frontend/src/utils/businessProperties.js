// Presentation projection only. Source identities and provenance are not modified.
const technical=/^(?:rdf_properties|rdf_types|prefix|kind|search_label|search_iri|source_tag|iri|uri|id|elementid|identity|labels|properties|__typename|x|y|vx|vy|fx|fy|index|depth|parent|data|height|level|children|synthetic|customer_approved|ontology_id|ontology_prefix|source_ontology|source_format|publication_id|publication_revision|artifact_sha256|updated_at|created_at|scope_key)$/i;
const local=key=>String(key).split(/[\/#]/).pop();
export function businessProperties(properties={}) {
  const rows=new Map();
  const add=(key,value)=>{
    const name=local(key);
    if(!name||technical.test(name)||/^(?:ontology|publication|artifact|source_task|import_task)_/i.test(name))return;
    const values=(Array.isArray(value)?value:[value]).map(v=>v&&typeof v==='object'?v.value:v)
      .filter(v=>['string','number','boolean'].includes(typeof v)).map(String).filter(v=>v&&!/[<>]/.test(v));
    if(!values.length)return;
    const label=name.replace(/([a-z0-9])([A-Z])/g,'$1 $2').replace(/_/g,' ');
    rows.set(label,[...new Set(values)].join('; '));
  };
  Object.entries(properties).forEach(([k,v])=>add(k,v));
  let rdf=properties.rdf_properties;
  if(typeof rdf==='string'&&rdf.length<=262144){try{rdf=JSON.parse(rdf);}catch{rdf=null;}}
  if(rdf&&typeof rdf==='object'&&!Array.isArray(rdf))Object.entries(rdf).forEach(([k,v])=>add(k,v));
  return [...rows].slice(0,40);
}
