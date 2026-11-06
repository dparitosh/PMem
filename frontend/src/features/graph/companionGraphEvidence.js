// Only retained typed evidence identities may focus an existing graph slice.
export function companionEvidenceIds(evidence, rootId) {
  const ids = new Set();
  for (const item of (Array.isArray(evidence) ? evidence : []).slice(0, 26)) {
    if (item?.evidence_type !== 'business_answer') continue;
    for (const row of (Array.isArray(item.rows) ? item.rows : []).slice(0, 20)) {
      for (const key of ['subject_id', 'requirement_id', 'part_id', 'pmi_id', 'node_id']) {
        if (typeof row?.[key] === 'string' && row[key].length < 512) ids.add(row[key]);
      }
    }
  }
  return rootId && ids.has(rootId) ? [...ids] : [];
}

export function focusCompanionEvidence(data, ids) {
  if (!ids?.length) return data;
  const selected = new Set(ids);
  const endpoint = value => typeof value === 'object' ? value?.elementId : value;
  return {...data,
    nodes: (data.nodes || []).filter(node => selected.has(node.elementId)),
    links: (data.links || []).filter(link => selected.has(endpoint(link.source)) && selected.has(endpoint(link.target))),
  };
}
