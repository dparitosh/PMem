

const SERVICE_ALIASES = {
  impact: 'change-impact',
  'change_impact': 'change-impact',
  changeImpact: 'change-impact',
  similar: 'similar-parts',
  'similar_parts': 'similar-parts',
  similarParts: 'similar-parts',
  process: 'manufacturing',
  manufacturing: 'manufacturing',
  mfg: 'manufacturing',
};

const normalizeRecommendationService = (service) => {
  const key = String(service || '').trim();
  return SERVICE_ALIASES[key] || key;
};

const extractRecommendationInput = (detail = {}) =>
  ['nodeName','name','label','displayName','value','query','partName','changeName']
    .map(key=>detail?.[key]).find(value=>typeof value==='string'&&value.trim()) || '';

const normalizeRecommendationResult = (service, payload) => {
  if(!payload||typeof payload!=='object'||Array.isArray(payload))throw new Error('Recommendation response is invalid. Retry after checking the graph service.');
  const data = payload;
  const isRecord=value=>value&&typeof value==='object'&&!Array.isArray(value);
  const invalid=()=>{throw new Error('Recommendation response contains invalid evidence. Check the service version and retry.');};
  const checkRecord=row=>{
    for(const key of ['total_direct','total_instances','total_related','impact_score','similarity_score','confidence','depth','score','count','engineering_matches','engineering_conflicts']){
      if(row[key]!=null&&(typeof row[key]!=='number'||!Number.isFinite(row[key])||row[key]<0))invalid();
    }
    for(const key of ['name','label','message','source_tag','process_name','part_name','file_name','relation','relation_type','link_type','class_name','rflp_layer','traceability_link','comparison_basis','reason','status','property','predicate','relationship_type','relationship_id']){
      if(row[key]!=null&&!['string','number','boolean'].includes(typeof row[key]))invalid();
    }
    for(const key of ['path_names','conflicts','source','candidate']){
      if(row[key]!=null&&(!Array.isArray(row[key])||row[key].some(value=>!['string','number','boolean'].includes(typeof value))))invalid();
    }
    for(const key of ['path','engineering_comparisons','configuration_review']){
      if(row[key]!=null){
        if(!Array.isArray(row[key])||row[key].some(value=>!isRecord(value)))invalid();
        if(key!=='path' && row[key].some(value=>!Array.isArray(value.source)||!Array.isArray(value.candidate)))invalid();
        row[key].forEach(checkRecord);
      }
    }
  };
  checkRecord(data);
  for(const key of ['change_entity','source_part','part','process_summary','decision_policy']){
    if(data[key]!=null&&!isRecord(data[key]))throw new Error('Recommendation response contains invalid evidence. Check the service version and retry.');
    if(data[key]!=null)checkRecord(data[key]);
  }
  if(data.process_summary?.by_type!=null){
    if(!isRecord(data.process_summary.by_type)||Object.values(data.process_summary.by_type).some(value=>!Array.isArray(value)))invalid();
  }
  for(const key of ['impacted_parts','assembly_impact','impacted_requirements','process_impacts','realization_chain','similar_parts','direct_processes','process_instances','related_part_processes','related_processes']){
    if(data[key]!=null&&(!Array.isArray(data[key])||data[key].some(row=>!isRecord(row))))throw new Error('Recommendation response contains invalid evidence rows. Check the service version and retry.');
    data[key]?.forEach(checkRecord);
  }
  if (service === 'change-impact') {
    return {
      ...data,
      impacted_parts: Array.isArray(data.impacted_parts) ? data.impacted_parts : [],
      assembly_impact: Array.isArray(data.assembly_impact) ? data.assembly_impact : [],
      impacted_requirements: Array.isArray(data.impacted_requirements) ? data.impacted_requirements : [],
      process_impacts: Array.isArray(data.process_impacts) ? data.process_impacts : [],
      realization_chain: Array.isArray(data.realization_chain) ? data.realization_chain : [],
    };
  }
  if (service === 'similar-parts') {
    return {
      ...data,
      similar_parts: Array.isArray(data.similar_parts) ? data.similar_parts : [],
    };
  }
  if (service === 'manufacturing') {
    return {
      ...data,
      direct_processes: Array.isArray(data.direct_processes) ? data.direct_processes : [],
      process_instances: Array.isArray(data.process_instances) ? data.process_instances : [],
      related_part_processes: Array.isArray(data.related_part_processes) ? data.related_part_processes : Array.isArray(data.related_processes) ? data.related_processes : [],
      process_summary: data.process_summary || {},
    };
  }
  return data;
};

export { SERVICE_ALIASES, normalizeRecommendationService, extractRecommendationInput, normalizeRecommendationResult };
