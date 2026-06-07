import React from 'react';
import { widgetCardStyle, widgetColors } from './widgetStyles';

export default function StatWidget({ label, value, status = 'neutral', icon: Icon }) {
  const tone = {
    ok: widgetColors.ok,
    warn: widgetColors.warn,
    danger: widgetColors.danger,
    neutral: widgetColors.blue,
  }[status] || widgetColors.blue;

  return (
    <section style={{ ...widgetCardStyle, padding: 9, minHeight: 64 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
        <div style={{ color: widgetColors.muted, fontSize: 11, fontWeight: 800, textTransform: 'uppercase' }}>
          {label}
        </div>
        {Icon && <Icon size={12} color={tone} strokeWidth={2.4} />}
      </div>
      <div style={{ color: widgetColors.text, fontSize: 20, fontWeight: 850, lineHeight: 1.15, marginTop: 5 }}>
        {value ?? '-'}
      </div>
    </section>
  );
}
