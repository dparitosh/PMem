import React, { useMemo } from 'react';
import { AgGridReact } from 'ag-grid-react';
import {
  ClientSideRowModelModule,
  ColumnAutoSizeModule,
  ModuleRegistry,
  NumberFilterModule,
  PaginationModule,
  QuickFilterModule,
  TextFilterModule,
  TooltipModule,
} from 'ag-grid-community';
import 'ag-grid-community/styles/ag-grid.css';
import 'ag-grid-community/styles/ag-theme-quartz.css';
import { widgetCardStyle, widgetColors } from './widgetStyles';

// Register only the table capabilities this shared widget exposes.  The
// previous AllCommunityModule pulled editing, infinite/server row models,
// export and other unused features into every lazy page that renders a grid.
ModuleRegistry.registerModules([
  ClientSideRowModelModule,
  ColumnAutoSizeModule,
  NumberFilterModule,
  PaginationModule,
  QuickFilterModule,
  TextFilterModule,
  TooltipModule,
]);

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
  onRowClicked = null,
}) {
  const usePagination = pagination ?? rows.length > paginationPageSize;
  const gridHeight = Math.max(Number(height) || 320, usePagination ? 360 : 320);
  const footerReserve = usePagination ? 48 : 0;
  const defaultColDef = useMemo(() => ({
    sortable: true,
    filter: true,
    resizable: true,
    floatingFilter: rows.length > 12,
    minWidth: 96,
    wrapHeaderText: false,
    suppressHeaderMenuButton: true,
    tooltipValueGetter: (params) => {
      const value = params?.value;
      return value === null || value === undefined || value === '' ? null : String(value);
    },
    cellStyle: {
      overflow: 'hidden',
      textOverflow: 'ellipsis',
      whiteSpace: 'nowrap',
    },
  }), [rows.length]);

  return (
    <section style={{ ...widgetCardStyle, overflow: 'hidden', minWidth: 0 }}>
      {(title || subtitle) && (
        <div style={{ padding: '10px 12px', borderBottom: `1px solid ${widgetColors.border}` }}>
          {title && <div style={{ fontSize: 13, fontWeight: 800, color: widgetColors.text }}>{title}</div>}
          {subtitle && <div style={{ marginTop: 4, fontSize: 11, color: widgetColors.muted }}>{subtitle}</div>}
        </div>
      )}
      {rows.length === 0 ? (
        <div style={{ height: gridHeight, display: 'grid', placeItems: 'center', color: widgetColors.muted, fontSize: 12 }}>
          {emptyLabel}
        </div>
      ) : (
        <div
          className="ag-theme-quartz depo-data-grid"
          style={{
            height: gridHeight + footerReserve,
            minHeight: (minGridHeight || gridHeight) + footerReserve,
            width: '100%',
            minWidth: 0,
            overflow: 'hidden',
            paddingBottom: footerReserve,
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
            paginationPageSizeSelector={[20, 25, 50, 100]}
            suppressCellFocus
            suppressMovableColumns
            suppressColumnVirtualisation={false}
            animateRows={false}
            rowHeight={36}
            headerHeight={38}
            tooltipShowDelay={200}
            onRowClicked={onRowClicked ? (event) => onRowClicked(event.data, event) : undefined}
          />
        </div>
      )}
    </section>
  );
}
