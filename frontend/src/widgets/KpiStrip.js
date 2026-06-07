import React from 'react';

export default function KpiStrip({ items = [] }) {
  return (
    <div className="depo-kpi-strip">
      {items.map((item) => (
        <div className="depo-kpi-cell" key={item.label}>
          <div className="depo-kpi-cell__label">{item.label}</div>
          <div className="depo-kpi-cell__value">{item.value ?? '-'}</div>
        </div>
      ))}
    </div>
  );
}
