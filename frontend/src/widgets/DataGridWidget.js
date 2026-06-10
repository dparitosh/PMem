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
  pagination = null,
  paginationPageSize = 20,
  minGridHeight = null,
}) {
  const usePagination = pagination ?? rows.length > paginationPageSize;
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
        <div
          className="ag-theme-quartz"
          style={{
            height,
            minHeight: minGridHeight || height,
            width: '100%',
            paddingBottom: usePagination ? 8 : 0,
            boxSizing: 'border-box',
          }}
        >
          <AgGridReact
            rowData={rows}
            columnDefs={columns}
            defaultColDef={defaultColDef}
            theme="legacy"
            quickFilterText={quickFilterText}
            pagination={usePagination}
            paginationPageSize={paginationPageSize}
            paginationPageSizeSelector={[20, 50, 100]}
            suppressCellFocus
            animateRows={false}
            rowHeight={36}
            headerHeight={38}
          />
        </div>
      )}
    </section>
  );
}
