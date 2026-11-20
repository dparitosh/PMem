import React, { useEffect, useState } from 'react';
import graphApi from '../services/graphApi';
import {apiErrorMessage} from '../utils/apiErrorMessage';
import EChartPanel from './EChartPanel';
import {apiClient} from '../services/apiClient';
import {buildSemanticServiceUrl} from '../config';

export default function OntologyOslcReport({ ontologyId, revision }) {
  const [report, setReport] = useState(null);
  const [error, setError] = useState('');
  const [lifecycle,setLifecycle]=useState(null),[lifecycleError,setLifecycleError]=useState('');
  useEffect(()=>{
    const controller=new AbortController();setLifecycle(null);setLifecycleError('');
    apiClient.get(buildSemanticServiceUrl('oslc','/api/v1/oslc/capabilities'),{signal:controller.signal,timeout:15000}).then(({data})=>{
      if(controller.signal.aborted)return;
      if(data?.scope!=='service_wide'||data.ontology_scoped!==false||!Array.isArray(data.capabilities)
         || data.capabilities.length!==3||new Set(data.capabilities.map(row=>row.id)).size!==3
         || !data.capabilities.every(row=>['trs','configuration','automation'].includes(row.id)&&typeof row.name==='string'
           && ['available','unavailable','disabled'].includes(row.status)&&row.counts&&typeof row.counts==='object'&&!Array.isArray(row.counts)&&typeof row.support==='string'
           && Object.values(row.counts).every(value=>Number.isSafeInteger(value)&&value>=0)
           && ['#/change-control','#/change-control?source=releases','#/data-flow'].includes(row.workspace)))throw new Error('Invalid lifecycle capability response');
      setLifecycle(data);
    }).catch(failure=>{if(!controller.signal.aborted)setLifecycleError(apiErrorMessage(failure,'OSLC lifecycle services are unavailable.'));});
    return()=>controller.abort();
  },[revision]);

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
      .catch(failure => { if (!controller.signal.aborted) setError(apiErrorMessage(failure, 'OSLC coverage is unavailable for this ontology.')); });
    return () => controller.abort();
  }, [ontologyId, revision]);
  const currentReport = report?.ontology_id === ontologyId ? report : null;
  const categories = currentReport?.categories || [];
  const option = currentReport?.resources > currentReport?.unmapped ? {
    tooltip: { trigger: 'axis' }, grid: { containLabel: true, left: 12, right: 12 },
    xAxis: { type: 'value', minInterval: 1 },
    yAxis: { type: 'category', data: categories.map(row => `${row.domain}: ${row.resource_type}`) },
    series: [{ type: 'bar', data: categories.map(row => row.count) }],
  } : null;
  return <section className="ontology-oslc-report" aria-label="Loaded ontology OSLC report">
    <section aria-label="OSLC lifecycle capabilities">
      <h3>Open Services for Lifecycle Collaboration (OSLC)</h3>
      <p>Platform-wide retained evidence · separate from ontology classification</p>
      {lifecycleError?<p role="alert">{lifecycleError}</p>:!lifecycle?<p role="status">Loading lifecycle services…</p>:<>
        <div className="ontology-oslc-report__table"><table><thead><tr><th>Capability</th><th>Status</th><th>Retained evidence</th><th>Workspace</th></tr></thead><tbody>
          {lifecycle.capabilities.map(row=><tr key={row.id}><th scope="row">{row.name}</th><td>{row.status}</td><td>{Object.entries(row.counts).map(([label,value])=>`${label}: ${value}`).join(' · ')||'—'}</td><td><a href={row.workspace} aria-label={`Open ${row.name} workspace`}>Open</a></td></tr>)}
        </tbody></table></div>
        <details><summary>Support scope</summary>{lifecycle.capabilities.map(row=><p key={row.id}><strong>{row.name}:</strong> {row.support}</p>)}</details>
      </>}
    </section>
    <h3>OSLC resource domains for the selected ontology</h3>
    {!ontologyId && <p>Select a loaded ontology above, including QIF, AP242 or ReqIF, to inspect its OSLC mappings.</p>}
    {error && <p role="alert">{error}</p>}
    {ontologyId && !report && !error && <p role="status">Loading ontology coverage…</p>}
    {currentReport && <>
      <p>{currentReport.resources} graph records · {currentReport.outgoing_links} outgoing links · {currentReport.unmapped} records without an RM/AM/CM/QM classification.</p>
      <EChartPanel title="OSLC domain resource coverage" description="Full selected-ontology counts using OSLC resource classification; categories may overlap." option={option} emptyMessage={currentReport?.resources ? "No RM/AM/CM/QM mappings in this scope. Automation, TRS and Configuration Management counts appear above." : "No graph records are loaded for this ontology."} />
      <div className="ontology-oslc-report__table"><table><thead><tr><th>OSLC domain</th><th>Resource type</th><th>Full count</th></tr></thead>
        <tbody>{categories.map(row => <tr key={row.resource_type}><td>{row.domain}</td><td>{row.resource_type}</td><td>{row.count}</td></tr>)}</tbody></table></div>
      {currentReport.notes.map(note => <p key={note}>{note}</p>)}
    </>}
  </section>;
}
