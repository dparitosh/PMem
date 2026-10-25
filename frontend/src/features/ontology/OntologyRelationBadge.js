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

export { REL_COLORS, RelBadge };
