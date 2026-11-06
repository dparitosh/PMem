import React from 'react';
import { UI_COLORS as C } from '../../styles/uiTokens';
export function exportCSV(rows, headers, filename) {
  const esc = v => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const lines = [headers.join(','), ...rows.map(r => headers.map(h => esc(r[h])).join(','))];
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}
export const TH = (extra = {}) => ({
  padding: '9px 14px',
  background: C.primary,
  color: '#fff',
  fontWeight: 700,
  fontSize: '11px',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  textAlign: 'left',
  whiteSpace: 'nowrap',
  borderRight: `1px solid ${C.primaryDark}`,
  position: 'sticky',
  top: 0,
  zIndex: 2,
  ...extra,
});
export const TD = (extra = {}) => ({
  padding: '8px 14px',
  borderBottom: `1px solid ${C.border}`,
  fontSize: '13px',
  color: C.textPrimary,
  verticalAlign: 'middle',
  ...extra,
});
