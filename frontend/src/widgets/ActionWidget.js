import React from 'react';
import { widgetCardStyle, widgetColors } from './widgetStyles';

export default function ActionWidget({ title, description, icon: Icon, actionLabel, onAction, disabled }) {
  return (
    <section style={{ ...widgetCardStyle, padding: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: 'flex', gap: 9, alignItems: 'flex-start' }}>
        {Icon && (
          <div style={{ width: 26, height: 26, display: 'grid', placeItems: 'center', borderRadius: 5, background: '#eef5fb' }}>
            <Icon size={14} color={widgetColors.blue} strokeWidth={2.3} />
          </div>
        )}
        <div style={{ minWidth: 0 }}>
          <div style={{ color: widgetColors.text, fontSize: 13, fontWeight: 800 }}>{title}</div>
          {description && <div style={{ color: widgetColors.muted, fontSize: 12, marginTop: 3 }}>{description}</div>}
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
            fontSize: 12,
            fontWeight: 800,
            padding: '7px 9px',
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
