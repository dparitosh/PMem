/*
 * DataTable: semantic <table> styled by tokens.css (.ui-data-table).
 *
 * Props:
 *   caption    required table caption (visible; names the table for screen readers)
 *   columns    [{ key: string, label: string, align?: 'left' | 'right' | 'center' }]
 *   rows       array of row objects
 *   rowKey     optional (row, index) => string; defaults to index
 *   renderCell optional (row, column) => node; defaults to row[column.key]
 *   empty      node shown when rows is empty (e.g. an EmptyState). Default: "No rows."
 *
 * Header cells use <th scope="col">. Empty state spans all columns in one row.
 */
import React from 'react';
import './tokens.css';

export default function DataTable({ caption, columns, rows = [], rowKey, renderCell, empty = 'No rows.' }) {
  const cell = (row, column) => (renderCell ? renderCell(row, column) : row[column.key]);
  return (
    <table className="ui-data-table">
      <caption>{caption}</caption>
      <thead>
        <tr>
          {columns.map((column) => (
            <th key={column.key} scope="col" style={column.align ? { textAlign: column.align } : undefined}>
              {column.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 ? (
          <tr>
            <td colSpan={columns.length} className="ui-data-table__empty">{empty}</td>
          </tr>
        ) : rows.map((row, index) => (
          <tr key={rowKey ? rowKey(row, index) : index}>
            {columns.map((column) => (
              <td key={column.key} style={column.align ? { textAlign: column.align } : undefined}>
                {cell(row, column)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
