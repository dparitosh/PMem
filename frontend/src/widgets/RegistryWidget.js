import React, { useMemo, useState } from 'react';
import DataGridWidget from './DataGridWidget';
import { widgetColors } from './widgetStyles';

function normalizeColumns(rows) {
  const first = rows?.[0] || {};
  return Object.keys(first).map((field) => ({
    field,
    headerName: field.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase()),
    valueFormatter: (params) => {
      if (Array.isArray(params.value)) return params.value.join(', ');
      if (typeof params.value === 'boolean') return params.value ? 'Yes' : 'No';
      return params.value ?? '';
    },
    flex: field === 'path' || field === 'name' || field === 'label' ? 1.4 : 1,
  }));
}

export default function RegistryWidget({ title, rows = [], columns, height = 300 }) {
  const [filter, setFilter] = useState('');
  const columnDefs = useMemo(() => columns || normalizeColumns(rows), [columns, rows]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <div style={{ color: widgetColors.text, fontSize: 15, fontWeight: 800 }}>{title}</div>
        <input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter"
          style={{
            width: 190,
            border: `1px solid ${widgetColors.border}`,
            borderRadius: 5,
            padding: '6px 8px',
            fontSize: 12,
            outline: 'none',
          }}
        />
      </div>
      <DataGridWidget rows={rows} columns={columnDefs} height={height} quickFilterText={filter} />
    </div>
  );
}
