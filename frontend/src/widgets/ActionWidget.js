import React from 'react';
import { widgetCardStyle, widgetColors } from './widgetStyles';

export default function ActionWidget({ title, description, icon: Icon, actionLabel, onAction, disabled }) {
  return (
    <section style={{ ...widgetCardStyle, padding: 9, display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', gap: 7, alignItems: 'flex-start' }}>
        {Icon && (
          <div style={{ width: 20, height: 20, display: 'grid', placeItems: 'center', borderRadius: 4, background: '#eef5fb' }}>
            <Icon size={11} color={widgetColors.blue} strokeWidth={2.5} />
          </div>
        )}
        <div style={{ minWidth: 0 }}>
          <div style={{ color: widgetColors.text, fontSize: 12, fontWeight: 850 }}>{title}</div>
          {description && <div style={{ color: widgetColors.muted, fontSize: 11, marginTop: 2, lineHeight: 1.35 }}>{description}</div>}
        </div>
      </div>
      {actionLabel && (
        <button
          type="button"
          onClick={onAction}
          disabled={disabled}
          style={{
            border: `1px solid ${widgetColors.blue}`,
            background: '#fff',
            color: widgetColors.blue,
            borderRadius: 5,
            fontSize: 11,
            fontWeight: 800,
            padding: '5px 8px',
            cursor: disabled ? 'not-allowed' : 'pointer',
            alignSelf: 'flex-start',
          }}
        >
          {actionLabel}
        </button>
      )}
    </section>
  );
}
