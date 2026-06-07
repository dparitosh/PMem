import React from 'react';
import ReportsTab from '../Components/ReportsTab';
import PageHeader from '../widgets/PageHeader';

export default function ReportsPage({ searchResults, chatResults, graphData }) {
  return (
    <div className="depo-page">
      <PageHeader
        eyebrow="Evidence and publishing"
        title="Review retained outputs from graph queries, imports, mappings, and validation"
        summary="Reports should communicate lineage and decisions, not only raw export files. This page is the publishing surface for engineering evidence."
        insights={[
          { label: 'Audience', value: 'Engineering, quality, architecture, program teams' },
          { label: 'Evidence types', value: 'Graph result, validation issue, mapping report, artifact bundle' },
          { label: 'Reuse target', value: 'Data dictionary, audit trail, and downstream analytics' },
        ]}
      />
      <section className="depo-panel">
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Reports Workbench</div>
            <div className="depo-panel__meta">Publish and inspect outputs generated from the current workspace context.</div>
          </div>
        </div>
        <div className="depo-panel__body">
          <ReportsTab searchResults={searchResults} chatResults={chatResults} graphData={graphData} />
        </div>
      </section>
    </div>
  );
}
