import React from 'react';
import RecommendationsTab from '../Components/RecommendationsTab';
import DataGridWidget from '../widgets/DataGridWidget';
import PageHeader from '../widgets/PageHeader';

const issueRows = [
  { control: 'Ontology validation', risk: 'Broken hierarchy, duplicate class intent, missing domain/range', evidence: 'SHACL or rule report', owner: 'Quality' },
  { control: 'Instance-to-ontology coverage', risk: 'Imported product data not semantically queryable', evidence: 'Mapping coverage matrix', owner: 'Ontology' },
  { control: 'Data dictionary completeness', risk: 'Users cannot interpret classes and properties consistently', evidence: 'Dictionary artifact', owner: 'Governance' },
  { control: 'Taxonomy coherence', risk: 'Conflicting product structures across source systems', evidence: 'Hierarchy and prefix review', owner: 'Architecture' },
];

export default function QualityPage({ setActiveTab }) {
  return (
    <div className="depo-page">
      <PageHeader
        eyebrow="Quality and governance"
        title="Turn graph content into trusted engineering evidence"
        summary="Quality is not a separate decoration layer; it is the control plane for ontology validity, mapping coverage, dictionary completeness, and product traceability."
        insights={[
          { label: 'Quality question', value: 'Can users trust the semantic answer?' },
          { label: 'Validation scope', value: 'Ontology, mappings, instance graph, dictionary' },
          { label: 'Action model', value: 'Find gaps, assign owner, retain evidence' },
        ]}
      />
      <DataGridWidget
        title="Quality Controls"
        subtitle="Controls are grouped by business risk and evidence, not by UI feature."
        rows={issueRows}
        height={240}
        columns={[
          { field: 'control', flex: 1.2 },
          { field: 'risk', flex: 2 },
          { field: 'evidence', flex: 1.3 },
          { field: 'owner' },
        ]}
      />
      <section className="depo-panel">
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Engineering Recommendations</div>
            <div className="depo-panel__meta">Use graph and semantic context for impact, similarity, and manufacturing guidance.</div>
          </div>
        </div>
        <div className="depo-panel__body">
          <RecommendationsTab setActiveTab={setActiveTab} />
        </div>
      </section>
    </div>
  );
}
