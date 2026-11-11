import React from "react";
import { UI_COLORS as C, UI_STATUS_COLORS } from "../../styles/uiTokens";

const REL_COLORS = {
  equivalentClass: UI_STATUS_COLORS.success,
  exactMatch: UI_STATUS_COLORS.success,
  closeMatch: UI_STATUS_COLORS.warn,
  predicate: UI_STATUS_COLORS.info,
  label: UI_STATUS_COLORS.violet,
  mapsTo: UI_STATUS_COLORS.accent,
};

function RelBadge({ type }) {
  const label = String(type || '').split(/[#/]/).pop() || type;
  const s = REL_COLORS[label] || { bg: C.bg, text: C.textSec, border: C.border };
  return (
    <span title={type} style={{
      display: 'inline-block', padding: '2px 10px', borderRadius: '12px',
      background: s.bg, color: s.text, border: `1px solid ${s.border}`,
      fontWeight: 700, fontSize: '11px', whiteSpace: 'nowrap',
    }}>{label}</span>
  );
}

const PLAIN_RELATION_NAMES = {
  subClassOf: 'Subclass of',
  domain: 'Domain',
  range: 'Range',
  equivalentClass: 'Equivalent class',
  exactMatch: 'Exact match',
  closeMatch: 'Close match',
  predicate: 'Predicate',
  label: 'Label',
  mapsTo: 'Maps to',
};

// Plain-language name for a relation type. The raw mapping_type (often a full IRI)
// should be shown in a title/tooltip, not as the primary label.
export function relationPlainName(type) {
  const local = String(type || '').split(/[#/]/).pop() || String(type || '');
  if (PLAIN_RELATION_NAMES[local]) return PLAIN_RELATION_NAMES[local];
  const words = local.replace(/([a-z0-9])([A-Z])/g, '$1 $2').replace(/[_-]+/g, ' ').trim().toLowerCase();
  return words ? words.charAt(0).toUpperCase() + words.slice(1) : 'Unknown relation';
}

export { REL_COLORS, RelBadge };
