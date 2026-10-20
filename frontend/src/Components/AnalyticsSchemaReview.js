import React, { useEffect, useState } from 'react';
import { apiClient } from '../services/apiClient';
import { buildSemanticServiceUrl } from '../config';
import { apiErrorMessage } from '../utils/apiErrorMessage';

export default function AnalyticsSchemaReview({ ontologyId }) {
  const [state, setState] = useState({});
  useEffect(() => {
    const controller = new AbortController();
    setState({ loading: Boolean(ontologyId) });
    if (ontologyId) apiClient.get(buildSemanticServiceUrl('ingestion', '/api/v1/reports/xsd-relational'),
      { params: { ontology_id: ontologyId }, signal: controller.signal, timeout: 60000 }).then(response => {
      if (response.data?.ontology_id !== ontologyId || !response.data?.analytics_schema_plan) throw new Error('The schema report does not match the selected ontology.');
      if (!controller.signal.aborted) setState({ report: response.data });
    }).catch(error => { if (!controller.signal.aborted) setState({ error: apiErrorMessage(error, 'Analytics schema report is unavailable.') }); });
    return () => controller.abort();
  }, [ontologyId]);
  const plan = state.report?.analytics_schema_plan;
  return <section aria-label="Analytics schema and business definitions">
    <h3>Analytics schema, dimensions and KPIs</h3>
    {!ontologyId && <p>Select an imported schema draft to inspect its structural analytics plan.</p>}
    {state.loading && <p role="status">Loading analytics schema…</p>}
    {state.error && <p role="alert">{state.error}</p>}
    {plan && <>
      <p>Schema: <strong>{plan.schema}</strong> · Execution: {plan.execution_mode}. This is a structural plan; warehouse deployment is a separate operation.</p>
      <h4>Entity tables ({plan.entity_tables?.length || 0})</h4>
      <div style={{ maxHeight: 300, overflow: 'auto' }}><table><thead><tr><th>Entity</th><th>Table</th><th>Grain</th></tr></thead><tbody>{(plan.entity_tables || []).map(table => <tr key={table.entity_id}><td>{table.entity_id}</td><td>{table.table}</td><td>{table.grain}</td></tr>)}</tbody></table></div>
      <h4>Dimensions and KPIs</h4>
      <p>Business definitions: {plan.business_analytics?.status || 'Unavailable'}. Source-schema classes are not automatically approved dimensions or KPIs.</p>
      <p>Define dimension keys, fact grain, measure expressions, units, aggregation and history policy in the approved XML analytics job below. Existing graph imports do not automatically populate these warehouse definitions.</p>
      <a href="#/data-flow">Open Data Flow to select an XML analytics job</a>
      {plan.ddl_blockers?.length > 0 && <p role="alert">Schema blockers: {plan.ddl_blockers.join('; ')}</p>}
      <details><summary>Review generated SQL</summary><pre style={{ maxHeight: 300, overflow: 'auto' }}>{Array.isArray(plan.sql) ? plan.sql.join('\n') : plan.sql}</pre></details>
    </>}
  </section>;
}
