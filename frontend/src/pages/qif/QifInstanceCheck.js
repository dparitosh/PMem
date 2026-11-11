import { useState } from 'react';
import { qifAPI } from '../../services/apiClient';
import { apiErrorMessage } from '../../utils/apiErrorMessage';

const panelStyle = { background: 'var(--ui-surface)', color: 'var(--ui-text)', border: '1px solid var(--ui-border)', borderRadius: 6, padding: 16, marginTop: 16 };
const SHOWN = 50;

// Checks one QIF 3.0 instance document against the schema and the QIF XSLT checks.
// Results are shown as returned by the backend; nothing is saved or published.
export default function QifInstanceCheck() {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  const run = async () => {
    setBusy(true); setError(''); setResult(null);
    try {
      const response = await qifAPI.checkInstance(file);
      setResult(response.data?.data ?? response.data ?? null);
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'The QIF instance could not be checked.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section style={panelStyle} aria-label="Check a QIF instance">
      <div className="depo-panel__title">Check a QIF instance file</div>
      <p className="depo-panel__meta">Validate one QIF 3.0 instance (.xml) against the schema and the QIF XSLT checks. Instances that reference other QIF documents are not supported.</p>
      <label htmlFor="qif-instance-file" style={{ display: 'block', fontSize: 12, fontWeight: 700, marginTop: 12, marginBottom: 6 }}>QIF instance file</label>
      <input id="qif-instance-file" type="file" accept=".xml,application/xml,text/xml" onChange={(event) => { setFile(event.target.files?.[0] || null); setResult(null); setError(''); }} />
      <button type="button" className="depo-action-button" disabled={!file || busy} onClick={run} style={{ marginTop: 12 }}>
        {busy ? 'Checking…' : 'Run QIF checks'}
      </button>
      {error && <p role="alert" style={{ color: 'var(--ui-status-danger)', marginTop: 12 }}>{error}</p>}
      {result && (
        <div style={{ marginTop: 12 }} aria-live="polite">
          <p><strong>{result.filename}</strong>: schema {result.xsd_valid ? 'valid' : 'invalid'}, {result.check_finding_count} check finding{result.check_finding_count === 1 ? '' : 's'}</p>
          {result.xsd_errors?.length > 0 && (
            <>
              <div className="depo-panel__meta">Schema errors</div>
              <ul>{result.xsd_errors.slice(0, SHOWN).map((item, index) => <li key={`xsd-${index}`}>Line {item.line}: {item.message}</li>)}</ul>
            </>
          )}
          {result.check_findings?.length > 0 && (
            <>
              <div className="depo-panel__meta">QIF check findings{result.check_finding_count > SHOWN ? ` (first ${SHOWN} shown)` : ''}</div>
              <ul>{result.check_findings.slice(0, SHOWN).map((item, index) => <li key={`check-${index}`}>{item.report}{item.node ? ` — ${item.node}` : ''}</li>)}</ul>
            </>
          )}
        </div>
      )}
    </section>
  );
}
