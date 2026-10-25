

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

const extractRecommendationInput = (detail = {}) => (
  detail.nodeName ||
  detail.name ||
  detail.label ||
  detail.displayName ||
  detail.value ||
  detail.query ||
  detail.partName ||
  detail.changeName ||
  ''
);

const normalizeRecommendationResult = (service, payload) => {
  const data = payload || {};
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
