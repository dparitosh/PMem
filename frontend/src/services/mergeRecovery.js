export async function recoverMergeResult(plan, readPublication) {
  const applied = plan?.applied_result;
  if (!applied) return null;
  const ontologyId = applied.ontology?.ontology_id;
  if (applied.status !== 'merged' || applied.preview_id !== plan.preview_id || !ontologyId) {
    throw new Error('Retained merge identity is incompatible. No write was replayed.');
  }
  const response = await readPublication(ontologyId);
  const publication = response?.data ?? response;
  if (publication?.ontology_id !== ontologyId) throw new Error('Publication scope does not match the retained merge. No write was replayed.');
  if (publication.status === 'publishing') {
    return {...applied, publication_status:'running', publication};
  }
  const receipt = publication.receipt;
  if (publication.status !== 'published' || receipt?.status !== 'published' || receipt.current !== true ||
      receipt.ontology_id !== ontologyId || !publication.publication_id || receipt.publication_id !== publication.publication_id ||
      ['resources','relationships'].some(key => !Number.isInteger(receipt[key]) || receipt[key] < 0)) {
    throw new Error('The merge is retained, but its current graph publication is unverified. Retry Resume saved plan; no write was replayed.');
  }
  return {...applied, publication_status:'published', publication};
}
