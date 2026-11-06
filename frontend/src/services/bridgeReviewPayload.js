// Reject malformed fields used by the review renderer before adopting a response.
export function bridgeReviewPayload(value) {
  const invalid = () => { throw new Error('Ontology agent review returned an invalid response.'); };
  const object = value => value && typeof value === 'object' && !Array.isArray(value);
  const strings = value => Array.isArray(value) && value.every(item => typeof item === 'string');
  if (!object(value) || !Array.isArray(value.steps)) invalid();
  for (const step of value.steps) {
    if (!object(step) || !object(step.result)) invalid();
    const result = step.result;
    for (const key of ['issues', 'alignment_items', 'alignment_candidates']) {
      if (result[key] !== undefined && (!Array.isArray(result[key]) || result[key].some(item => !object(item)))) invalid();
    }
    for (const item of [...(result.alignment_items || []), ...(result.alignment_candidates || [])]) {
      for (const key of ['source', 'status', 'target_iri', 'target_type', 'evidence']) {
        if (item[key] !== undefined && typeof item[key] !== 'string') invalid();
      }
      if (item.unresolved_checks !== undefined && !strings(item.unresolved_checks)) invalid();
    }
    for (const key of ['unmatched_count', 'ambiguous_count']) {
      if (result[key] !== undefined && (!Number.isSafeInteger(result[key]) || result[key] < 0)) invalid();
    }
    if (result.llm !== undefined) {
      const llm = result.llm;
      if (!object(llm) || (llm.text !== undefined && typeof llm.text !== 'string')) invalid();
      if (llm.review !== undefined) {
        const review = llm.review;
        if (!object(review) || typeof review.limitations !== 'string' || !Array.isArray(review.questions)) invalid();
        for (const question of review.questions) {
          if (!object(question) || typeof question.question !== 'string' || !strings(question.evidence_iris)) invalid();
        }
      }
    }
  }
  return value;
}
