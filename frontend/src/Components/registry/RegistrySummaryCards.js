import React from 'react';

function Summary({ icon, label, value }) {
  return (
    <div style={{ border: '1px solid #d9e2ec', borderRadius: 8, padding: '10px 12px', background: '#f8fafc' }}>
      <div style={{ display: 'flex', gap: 7, alignItems: 'center', color: '#52606d', fontSize: 11, fontWeight: 700 }}>{icon}{label}</div>
      <div style={{ marginTop: 4, color: '#102a43', fontSize: 20, fontWeight: 800 }}>{value}</div>
    </div>
  );
}

export default function RegistrySummaryCards({ items }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8 }}>
      {items.map((item) => (
        <Summary key={item.label} icon={item.icon} label={item.label} value={item.value} />
      ))}
    </div>
  );
}
