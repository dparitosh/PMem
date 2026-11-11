// Presentation only: never rewrite API payloads, stored provenance or identities.
export function businessText(value) {
  if (value == null) return '';
  return String(value).split(/(https?:\/\/[^\s<>]+|\[evidence:[^\]\n]+\]|`[^`]*`)/g)
    .map((part, index) => index % 2 ? part : part
      .replace(/\bNeo4j\b/gi, 'knowledge graph')
      .replace(/\bSemantica\b/gi, 'semantic analysis'))
    .join('');
}
