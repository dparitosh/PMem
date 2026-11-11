import { useState } from 'react';
import { qifAPI } from '../../services/apiClient';
import { apiErrorMessage } from '../../utils/apiErrorMessage';

const panelStyle = { background: 'var(--ui-surface)', color: 'var(--ui-text)', border: '1px solid var(--ui-border)', borderRadius: 6, padding: 16, marginTop: 16 };
const SHOWN = 50;

function label(item) {
  if (!item) return '';
  return `${item.name || item.id}${item.id ? ` (${item.id})` : ''}`;
}

// Runs the QIF XSLT checks on one QIF 3.0 instance and, when an AP242 file is
// given, compares the QIF Bill of Characteristics with the AP242 PMI. Results are
// shown as returned by the backend; nothing is saved or published.
export default function QifInstanceCheck() {
  const [file, setFile] = useState(null);
  const [ap242File, setAp242File] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [boc, setBoc] = useState(null);

  const run = async () => {
    setBusy(true); setError(''); setResult(null); setBoc(null);
    try {
      const response = await qifAPI.checkInstance(file);
      setResult(response.data?.data ?? response.data ?? null);
      if (ap242File) {
        const bocResponse = await qifAPI.checkBoc(file, ap242File);
        setBoc(bocResponse.data?.data ?? bocResponse.data ?? null);
      }
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'The QIF instance could not be checked.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section style={panelStyle} aria-label="Check a QIF instance">
      <div className="depo-panel__title">Check a QIF instance file</div>
      <p className="depo-panel__meta">Run the QIF 3.0 XSLT checks on one instance (.xml). Optionally add the AP242 STEP file it came from to compare the Bill of Characteristics. Instances that reference other QIF documents are not supported.</p>
      <label htmlFor="qif-instance-file" style={{ display: 'block', fontSize: 12, fontWeight: 700, marginTop: 12, marginBottom: 6 }}>QIF instance file</label>
      <input id="qif-instance-file" type="file" accept=".xml,application/xml,text/xml" onChange={(event) => { setFile(event.target.files?.[0] || null); setResult(null); setBoc(null); setError(''); }} />
      <label htmlFor="qif-ap242-file" style={{ display: 'block', fontSize: 12, fontWeight: 700, marginTop: 12, marginBottom: 6 }}>AP242 file (optional)</label>
      <input id="qif-ap242-file" type="file" accept=".stp,.step,.stpx,.xml,application/xml,text/xml" onChange={(event) => { setAp242File(event.target.files?.[0] || null); setBoc(null); }} />
      <button type="button" className="depo-action-button" disabled={!file || busy} onClick={run} style={{ marginTop: 12 }}>
        {busy ? 'Checking…' : (ap242File ? 'Run QIF checks and BOC comparison' : 'Run QIF checks')}
      </button>
      {error && <p role="alert" style={{ color: 'var(--ui-status-danger)', marginTop: 12 }}>{error}</p>}
      {result && (
        <div style={{ marginTop: 12 }} aria-live="polite">
          <p><strong>{result.filename}</strong>: {result.check_finding_count} QIF check finding{result.check_finding_count === 1 ? '' : 's'}</p>
          {result.check_findings?.length > 0 && (
            <>
              <div className="depo-panel__meta">QIF check findings{result.check_finding_count > SHOWN ? ` (first ${SHOWN} shown)` : ''}</div>
              <ul>{result.check_findings.slice(0, SHOWN).map((item, index) => <li key={`check-${index}`}>{item.report}{item.node ? ` — ${item.node}` : ''}</li>)}</ul>
            </>
          )}
        </div>
      )}
      {boc && (
        <div style={{ marginTop: 16 }} aria-live="polite">
          <div className="depo-panel__title">Bill of Characteristics: QIF vs AP242</div>
          <p>{boc.summary.matched} matched, {boc.summary.ambiguous} ambiguous, {boc.summary.ap242_dimensions} AP242 dimensions, {boc.summary.qif_characteristics} QIF characteristics, {boc.summary.ap242_tolerances} AP242 tolerances for review.</p>
          {boc.matched?.length > 0 && (
            <>
              <div className="depo-panel__meta">Matched by nominal value</div>
              <ul>{boc.matched.slice(0, SHOWN).map((item, index) => <li key={`match-${index}`}>{label(item.ap242)} ↔ {label(item.qif)}: {item.nominal_value} {item.qif_unit || ''}</li>)}</ul>
            </>
          )}
          {boc.ambiguous?.length > 0 && (
            <>
              <div className="depo-panel__meta">Ambiguous (not matched)</div>
              <ul>{boc.ambiguous.slice(0, SHOWN).map((item, index) => <li key={`amb-${index}`}>{label(item.ap242)} = {item.nominal_value}: {item.qif_candidates.length} QIF candidates</li>)}</ul>
            </>
          )}
          {boc.ap242_dimensions_unmatched?.length > 0 && (
            <>
              <div className="depo-panel__meta">AP242 dimensions not in the QIF Bill of Characteristics</div>
              <ul>{boc.ap242_dimensions_unmatched.slice(0, SHOWN).map((item, index) => <li key={`apu-${index}`}>{label(item)}: {item.reason}</li>)}</ul>
            </>
          )}
          {boc.qif_characteristics_unmatched?.length > 0 && (
            <>
              <div className="depo-panel__meta">QIF characteristics not matched to AP242</div>
              <ul>{boc.qif_characteristics_unmatched.slice(0, SHOWN).map((item, index) => <li key={`qu-${index}`}>{label(item)}</li>)}</ul>
            </>
          )}
          {boc.ap242_tolerances_for_review?.length > 0 && (
            <>
              <div className="depo-panel__meta">AP242 tolerances for manual review</div>
              <ul>{boc.ap242_tolerances_for_review.slice(0, SHOWN).map((item, index) => <li key={`tol-${index}`}>{label(item)}</li>)}</ul>
            </>
          )}
          <div className="depo-panel__meta">Scope</div>
          <ul>{(boc.scope_notes || []).map((note, index) => <li key={`note-${index}`}>{note}</li>)}</ul>
        </div>
      )}
    </section>
  );
}
