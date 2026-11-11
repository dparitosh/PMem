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

export default function RegistryWidget({ title, rows = [], columns, height = 300, showFilter = true, onRowClicked = null }) {
  const [filter, setFilter] = useState('');
  const columnDefs = useMemo(() => columns || normalizeColumns(rows), [columns, rows]);

  return (
    <div className="depo-registry-widget" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div className="depo-registry-widget__header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
        <h3 style={{ margin: 0, color: widgetColors.text, fontSize: 15, fontWeight: 700 }}>{title}</h3>
        {showFilter && <input
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder="Filter"
          aria-label={`Filter ${title || 'records'}`}
          style={{
            width: 190,
            border: `1px solid ${widgetColors.border}`,
            borderRadius: 5,
            padding: '6px 8px',
            fontSize: 12,
          }}
        />}
      </div>
      <DataGridWidget appearance="embedded" ariaLabel={title} rows={rows} columns={columnDefs} height={height} quickFilterText={showFilter ? filter : ''} onRowClicked={onRowClicked} />
    </div>
  );
}
