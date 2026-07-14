const OWLREADY_TEMP_SEGMENT_RE = /^tmp[a-z0-9_]{6,}[.:](.+)$/i;
const OWLREADY_TEMP_TOKEN_RE = /^tmp[a-z0-9_]{6,}$/i;

export function ontologyFragment(value = '') {
  return String(value || '').trim().split(/[/#]/).pop() || '';
}

export function stripOwlreadyTempSegment(value = '') {
  const raw = String(value || '').trim();
  const match = raw.match(OWLREADY_TEMP_SEGMENT_RE);
  return match ? match[1] : raw;
}

export function cleanOntologyPrefix(value = '', fallback = '') {
  const raw = String(value || '').trim();
  if (!raw || OWLREADY_TEMP_TOKEN_RE.test(raw)) return String(fallback || '').trim();
  return stripOwlreadyTempSegment(raw);
}

export function ontologyDisplayName(ref = {}) {
  const raw = String(
    ref?.label
    || ref?.name
    || ref?.local_name
    || ontologyFragment(ref?.iri || ref?.uri)
    || ontologyFragment(ref?.term_id || ref?.id)
    || ''
  ).trim();
  return stripOwlreadyTempSegment(raw);
}

export function ontologyTermId(ref = {}, prefixHint = '') {
  const prefix = cleanOntologyPrefix(ref?.ontology_prefix || ref?.prefix, prefixHint);
  const uri = String(ref?.iri || ref?.uri || '').trim();
  const rawTermId = String(ref?.term_id || ref?.id || '').trim();
  const termLocal = rawTermId.includes(':') ? rawTermId.split(':').slice(1).join(':') : rawTermId;
  const hasTempLocal = OWLREADY_TEMP_SEGMENT_RE.test(termLocal);
  const local = ontologyDisplayName({
    ...ref,
    label: ref?.local_name || ref?.label || (uri ? ontologyFragment(uri) : stripOwlreadyTempSegment(termLocal)),
  });

  if (!hasTempLocal && rawTermId) return rawTermId;
  if (prefix && local) return `${prefix}:${local}`;
  return uri || local || rawTermId;
}

export function normalizeOntologyBrowserNode(node = {}, prefixHint = '') {
  const label = ontologyDisplayName(node);
  const termId = ontologyTermId({ ...node, label }, prefixHint);
  return {
    ...node,
    term_id: termId,
    id: termId,
    label,
    ontology_prefix: cleanOntologyPrefix(node.ontology_prefix || node.prefix, prefixHint),
  };
}
