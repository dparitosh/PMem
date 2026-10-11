import React, { useEffect, useState } from 'react';
import graphApi from '../services/graphApi';
import EChartPanel from './EChartPanel';

export default function OntologyOslcReport({ ontologyId, revision }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setReport(null); setError('');
    if (ontologyId) graphApi.getOntologyReport(ontologyId, controller.signal)
      .then(response => {
        const data = response.data;
        const validCount = value => Number.isSafeInteger(value) && value >= 0;
        if (data?.ontology_id !== ontologyId || data.sampled !== false
          || !['resources', 'outgoing_links', 'unmapped'].every(key => validCount(data[key]))
          || !Array.isArray(data.categories) || !data.categories.every(row =>
            typeof row.resource_type === 'string' && typeof row.domain === 'string' && validCount(row.count))
          || !Array.isArray(data.notes) || !data.notes.every(note => typeof note === 'string')) {
          throw new Error('Invalid ontology report response');
        }
        if (!controller.signal.aborted) setReport(data);
      })
      .catch(() => { if (!controller.signal.aborted) setError('OSLC report unavailable. Check API access, ontology registry and graph service.'); });
    return () => controller.abort();
  }, [ontologyId, revision]);
  const currentReport = report?.ontology_id === ontologyId ? report : null;
  const categories = currentReport?.categories || [];
  const option = currentReport?.resources > 0 ? {
    tooltip: { trigger: 'axis' }, grid: { containLabel: true, left: 12, right: 12 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: categories.map(row => `${row.domain}: ${row.resource_type}`) },
    series: [{ type: 'bar', data: categories.map(row => row.count) }],
  } : null;
  return <section className="ontology-oslc-report" aria-label="Loaded ontology OSLC report">
    <h3>Loaded ontology — OSLC coverage</h3>
    {!ontologyId && <p>Select a loaded ontology above, including QIF, AP242 or ReqIF, to inspect its OSLC mappings.</p>}
    {error && <p role="alert">{error}</p>}
    {ontologyId && !report && !error && <p role="status">Loading ontology coverage…</p>}
    {currentReport && <>
      <p>{currentReport.resources} graph records · {currentReport.outgoing_links} outgoing links · {currentReport.unmapped} records without an RM/AM/CM/QM classification.</p>
      <EChartPanel title="OSLC domain resource coverage" description="Full selected-ontology counts using OSLC resource classification; categories may overlap." option={option} emptyMessage="No graph records are loaded for this ontology." />
      <div className="ontology-oslc-report__table"><table><thead><tr><th>OSLC domain</th><th>Resource type</th><th>Full count</th></tr></thead>
        <tbody>{categories.map(row => <tr key={row.resource_type}><td>{row.domain}</td><td>{row.resource_type}</td><td>{row.count}</td></tr>)}</tbody></table></div>
      {currentReport.notes.map(note => <p key={note}>{note}</p>)}
    </>}
  </section>;
}
