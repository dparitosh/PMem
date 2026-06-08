import React, { useMemo } from 'react';
import { AgGridReact } from 'ag-grid-react';
import { AllCommunityModule, ModuleRegistry } from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';
import { widgetCardStyle, widgetColors } from './widgetStyles';

ModuleRegistry.registerModules([AllCommunityModule]);

export default function DataGridWidget({
  title,
  subtitle,
  rows = [],
  columns = [],
  height = 320,
  quickFilterText = '',
  emptyLabel = 'No records available',
}) {
  const defaultColDef = useMemo(() => ({
    sortable: true,
    filter: true,
    resizable: true,
    floatingFilter: rows.length > 12,
    minWidth: 120,
  }), [rows.length]);

  return (
    <section style={{ ...widgetCardStyle, overflow: 'hidden' }}>
      {(title || subtitle) && (
        <div style={{ padding: '10px 12px', borderBottom: `1px solid ${widgetColors.border}` }}>
          {title && <div style={{ fontSize: 13, fontWeight: 800, color: widgetColors.text }}>{title}</div>}
        </div>
      )}
      {rows.length === 0 ? (
        <div style={{ height, display: 'grid', placeItems: 'center', color: widgetColors.muted, fontSize: 12 }}>
          {emptyLabel}
        </div>
      ) : (
        <div className="ag-theme-quartz" style={{ height, width: '100%' }}>
          <AgGridReact
            rowData={rows}
            columnDefs={columns}
            defaultColDef={defaultColDef}
            theme="legacy"
            quickFilterText={quickFilterText}
            pagination={rows.length > 20}
            paginationPageSize={20}
            suppressCellFocus
            animateRows={false}
          />
        </div>
      )}
    </section>
  );
}
