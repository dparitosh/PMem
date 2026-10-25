import React from 'react';
import { UI_COLORS as C } from '../../styles/uiTokens';
import { getCredentialProfile } from '../../services/serviceAuth';

// Read-only review rendering; the workspace owns approval and commit requests.
export default function ImportLoadReview({ confirmingImport, previewData, setConfirmingImport, preCheck, commitApprover, setCommitApprover, commitImport }) {
  return (confirmingImport && previewData && (
        <div role="dialog" aria-modal="true" aria-label="Review import before loading" style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div style={{
            background: C.surface,
            borderRadius: '8px',
            padding: '24px',
            maxWidth: '800px',
            maxHeight: '80vh',
            overflow: 'auto',
            boxShadow: '0 10px 40px rgba(0,0,0,0.2)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '700', color: C.textPrimary }}>
                Preview
              </h3>
              <button
                onClick={() => { setConfirmingImport(null);  }}
                style={{
                  background: 'transparent',
                  border: 'none',
                  fontSize: '20px',
                  cursor: 'pointer',
                  color: C.textMuted,
                }}
              >
                Close
              </button>
            </div>

            {/* Preview stats */}
            <div style={{
              background: C.bg,
              border: `1px solid ${C.border}`,
              borderRadius: '4px',
              padding: '12px',
              marginBottom: '16px',
            }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', fontSize: '12px' }}>
                <div>
                  <div style={{ color: C.textMuted, marginBottom: '4px' }}>Total Rows</div>
                  <div style={{ fontSize: '16px', fontWeight: '700', color: C.primaryText }}>
                    {previewData.row_count ?? 0}
                  </div>
                </div>
                <div>
                  <div style={{ color: C.textMuted, marginBottom: '4px' }}>Columns</div>
                  <div style={{ fontSize: '16px', fontWeight: '700', color: C.primaryText }}>
                    {(previewData.columns || []).length}
                  </div>
                </div>
                <div>
                  <div style={{ color: C.textMuted, marginBottom: '4px' }}>Node Labels</div>
                  <div style={{ fontSize: '16px', fontWeight: '700', color: C.primaryText }}>
                    {previewData.auto_schema?.nodes?.length || 1}
                  </div>
                </div>
              </div>
            </div>

            {/* Column list */}
            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', fontWeight: '600', color: C.textPrimary, marginBottom: '8px' }}>
                Columns
              </div>
              <div style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '6px',
              }}>
                {(previewData.columns || []).map((col, idx) => (
                  <span
                    key={`col-${idx}-${col}`}
                    style={{
                      background: C.primaryLight,
                      color: C.primaryText,
                      padding: '4px 8px',
                      borderRadius: '3px',
                      fontSize: '11px',
                      fontWeight: '500',
                    }}
                  >
                    {col}
                  </span>
                ))}
              </div>
            </div>

            {/* Sample rows */}
            <div style={{ marginBottom: '16px' }}>
              <div style={{ fontSize: '12px', fontWeight: '600', color: C.textPrimary, marginBottom: '8px' }}>
                Sample Data (First 5 Rows)
              </div>
              <div style={{
                background: C.bg,
                border: `1px solid ${C.border}`,
                borderRadius: '4px',
                overflow: 'auto',
                maxHeight: '200px',
              }}>
                <table style={{ width: '100%', fontSize: '11px', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: `1px solid ${C.border}`, background: C.bg }}>
                      {(previewData.columns || []).slice(0, 5).map((col, colIdx) => (
                        <th
                          key={`header-${colIdx}-${col}`}
                          style={{
                            padding: '8px',
                            textAlign: 'left',
                            fontWeight: '600',
                            color: C.textPrimary,
                            borderRight: colIdx < 4 ? `1px solid ${C.border}` : 'none',
                          }}
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(previewData.sample_rows || []).map((row, rowIdx) => (
                      <tr key={`row-${rowIdx}`} style={{ borderBottom: `1px solid ${C.border}` }}>
                        {(previewData.columns || []).slice(0, 5).map((col, colIdx) => (
                          <td
                            key={`cell-${rowIdx}-${col}`}
                            style={{
                              padding: '8px',
                              borderRight: colIdx < 4 ? `1px solid ${C.border}` : 'none',
                              color: C.textPrimary,
                            }}
                          >
                            {String(row[col] || '-').substring(0, 30)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Pre-commit checks */}
            <div style={{
              background: preCheck?.ready === false ? '#FFEBEE' : preCheck?.ready === true ? '#E8F5E9' : C.bg,
              border: `1px solid ${preCheck?.ready === false ? '#FFCDD2' : preCheck?.ready === true ? '#C8E6C9' : C.border}`,
              borderRadius: '6px',
              padding: '10px 14px',
              marginBottom: '12px',
              fontSize: '12px',
            }}>
              {preCheck?.loading && (
                <div style={{ color: C.textSec, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ display: 'inline-block', width: 12, height: 12, border: `2px solid ${C.border}`, borderTop: `2px solid ${C.primary}`, borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
                  Checking status...
                  <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
                </div>
              )}
              {!preCheck?.loading && preCheck && (
                <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 700, color: preCheck.ready ? '#067647' : '#B42318' }}>
                    {preCheck.ready ? 'Ready to commit' : 'Cannot commit'}
                  </span>
                  {preCheck.checks?.neo4j && (
                    <span style={{ color: preCheck.checks.neo4j.ok ? '#067647' : '#B42318' }}>
                      {preCheck.checks.neo4j.ok ? 'OK' : 'Failed'} Neo4j: {preCheck.checks.neo4j.message || (preCheck.checks.neo4j.ok ? 'Connected' : 'Unreachable')}
                    </span>
                  )}
                  {preCheck.checks?.task && (
                    <span style={{ color: preCheck.checks.task.ok ? '#067647' : '#B42318' }}>
                      {preCheck.checks.task.ok ? 'OK' : 'Failed'} Task: {preCheck.checks.task.status}
                      {preCheck.checks.task.rows ? `  /  ${preCheck.checks.task.rows.toLocaleString()} rows` : ''}
                    </span>
                  )}
                  {!preCheck.ready && preCheck.reason && (
                    <span style={{ color: '#B42318', fontStyle: 'italic' }}>{preCheck.reason}</span>
                  )}
                </div>
              )}
              {!preCheck && (
                <span style={{ color: C.textMuted }}>Checks run before load.</span>
              )}
            </div>

            <details style={{ marginBottom: '12px', fontSize: '12px', color: C.textSec }}>
              <summary>Approval credentials (required by token authentication for loading)</summary>
              <p style={{ margin: '8px 0' }}>The key is managed in Admin / Service credentials. Enter the approver here; confirmation is still required.</p>
              <label style={{ display: 'block', marginBottom: '6px' }}>
                Approver
                <input aria-label="Import approver" value={commitApprover} onChange={(event) => setCommitApprover(event.target.value)} autoComplete="off" style={{ display: 'block', width: '100%', boxSizing: 'border-box', marginTop: '3px' }} />
              </label>
              <label style={{ display: 'block' }}>
                Approval API key: configured in Admin / Service credentials
              </label>
            </details>

            {/* Actions */}
            <div style={{
              display: 'flex',
              gap: '8px',
              justifyContent: 'flex-end',
            }}>
              <button
                onClick={() => { setConfirmingImport(null);  }}
                style={{
                  padding: '8px 16px',
                  background: C.border,
                  color: C.textPrimary,
                  border: 'none',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => commitImport(confirmingImport)}
                disabled={preCheck?.loading || preCheck?.ready !== true || (getCredentialProfile('INGESTION_WRITE_TOKEN') && !commitApprover.trim())}
                style={{
                  padding: '8px 16px',
                  background: (preCheck?.loading || preCheck?.ready === false) ? C.textMuted : C.green,
                  color: '#fff',
                  border: 'none',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: '600',
                  cursor: (preCheck?.loading || preCheck?.ready === false) ? 'not-allowed' : 'pointer',
                }}
              >
                {preCheck?.loading ? 'Checking...' : 'Load to Neo4j'}
              </button>
            </div>
          </div>
        </div>
      ));
}
