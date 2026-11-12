import { useEffect, useRef, useState } from 'react';
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

  const generation = useRef(0), request = useRef(null);
  const invalidate = () => {
    generation.current++; request.current?.abort(); request.current = null;
    setBusy(false); setResult(null); setBoc(null); setError('');
  };
  useEffect(() => {
    const events=['depo:session-replaced','depo:session-expired','depo:credentials-cleared','depo:credentials-changed'];
    events.forEach(event=>window.addEventListener(event,invalidate));
    return () => { generation.current++; request.current?.abort(); events.forEach(event=>window.removeEventListener(event,invalidate)); };
  }, []);
  const run = async () => {
    if (!file || request.current) return;
    const controller = new AbortController(); request.current = controller;
    const currentGeneration = ++generation.current;
    const current = () => !controller.signal.aborted && generation.current === currentGeneration;
    const qifFile = file, designFile = ap242File;
    setBusy(true); setError(''); setResult(null); setBoc(null);
    try {
      const response = await qifAPI.checkInstance(qifFile, { signal: controller.signal });
      if (!current()) return;
      const checked = response.data?.data ?? response.data;
      if (!checked || checked.filename !== qifFile.name || !Number.isInteger(checked.check_finding_count) || !Array.isArray(checked.check_findings)) throw new Error('The QIF check response did not identify the selected file and findings.');
      setResult(checked);
      if (designFile) {
        const bocResponse = await qifAPI.checkBoc(qifFile, designFile, { signal: controller.signal });
        if (!current()) return;
        const compared = bocResponse.data?.data ?? bocResponse.data;
        if (!compared?.summary || !Number.isInteger(compared.summary.matched) || !Array.isArray(compared.matched)) throw new Error('The comparison response did not contain valid pairing evidence.');
        if ((compared.qif_filename && compared.qif_filename !== qifFile.name) || (compared.ap242_filename && compared.ap242_filename !== designFile.name)) throw new Error('The comparison response belongs to different source files.');
        setBoc(compared);
      }
    } catch (requestError) {
      if (current()) setError(apiErrorMessage(requestError, 'The QIF instance could not be checked.'));
    } finally {
      if (current()) { request.current = null; setBusy(false); }
    }
  };

  return (
    <section style={panelStyle} aria-label="Check a QIF instance">
      <div className="depo-panel__title">Check a QIF instance file</div>
      <p className="depo-panel__meta">Run the QIF 3.0 XSLT checks on one instance (.xml). Optionally add the AP242 STEP file it came from to compare the Bill of Characteristics. Instances that reference other QIF documents are not supported.</p>
      <label htmlFor="qif-instance-file" style={{ display: 'block', fontSize: 12, fontWeight: 700, marginTop: 12, marginBottom: 6 }}>QIF instance file</label>
      <input id="qif-instance-file" type="file" accept=".xml,application/xml,text/xml" onChange={(event) => { invalidate(); setFile(event.target.files?.[0] || null); }} />
      <label htmlFor="qif-ap242-file" style={{ display: 'block', fontSize: 12, fontWeight: 700, marginTop: 12, marginBottom: 6 }}>AP242 file (optional)</label>
      <input id="qif-ap242-file" type="file" accept=".stp,.step,.stpx,.xml,application/xml,text/xml" onChange={(event) => { invalidate(); setAp242File(event.target.files?.[0] || null); }} />
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
          <p>{boc.summary.matched} nominally paired, {boc.summary.ambiguous} ambiguous, {boc.summary.ap242_dimensions} AP242 dimensions, {boc.summary.qif_characteristics} QIF characteristics, {boc.summary.ap242_tolerances} AP242 tolerances for review.</p>
          {boc.matched?.length > 0 && (
            <>
              <div className="depo-panel__meta">Paired by nominal value — not a conformance verdict</div>
              <p>Bounds conflicts: {boc.summary.bounds_mismatch ?? 'Not reported'}; unit conflicts: {boc.summary.unit_mismatch ?? 'Not reported'}. Missing evidence is not agreement. No unit conversion is applied.</p>
              <ul>{boc.matched.slice(0, SHOWN).map((item, index) => <li key={`match-${index}`}>
                <strong>{label(item.ap242)} ↔ {label(item.qif)}</strong>: nominal {item.nominal_value}
                <div>Units: {item.unit_status || 'not_available'} · AP242: {item.ap242_values?.unit || 'Not recorded'}; QIF: {item.qif_values?.unit || 'Not recorded'}</div>
                <div>Bounds: {item.bounds_status || 'not_available'} · AP242: {item.ap242_values?.bounds?.lower ?? 'Not recorded'} to {item.ap242_values?.bounds?.upper ?? 'Not recorded'}; QIF: {item.qif_values?.lower_limit ?? 'Not recorded'} to {item.qif_values?.upper_limit ?? 'Not recorded'}</div>
              </li>)}</ul>
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
