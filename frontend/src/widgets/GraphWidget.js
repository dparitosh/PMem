import React from 'react';
import { widgetCardStyle } from './widgetStyles';

export default function GraphWidget({ title = 'Graph Explorer', subtitle, children, minHeight = 520 }) {
  return (
    <section style={{ ...widgetCardStyle, display: 'flex', flexDirection: 'column', minHeight, overflow: 'hidden' }}>
      <div style={{ flex: '1 1 auto', minHeight: 0, position: 'relative' }}>
        {children}
      </div>
    </section>
  );
}
