import React from 'react';
import { widgetCardStyle, widgetColors } from './widgetStyles';

export default function GraphWidget({ title = 'Graph Explorer', subtitle, children, minHeight = 520 }) {
  return (
    <section style={{ ...widgetCardStyle, display: 'flex', flexDirection: 'column', minHeight, overflow: 'hidden' }}>
      {(title || subtitle) && (
        <div style={{ padding: '10px 12px', borderBottom: `1px solid ${widgetColors.border}` }}>
          <div style={{ color: widgetColors.text, fontSize: 13, fontWeight: 800 }}>{title}</div>
          {subtitle && <div style={{ color: widgetColors.muted, fontSize: 12, marginTop: 2 }}>{subtitle}</div>}
        </div>
      )}
      <div style={{ flex: '1 1 auto', minHeight: 0, position: 'relative' }}>
        {children}
      </div>
    </section>
  );
}
