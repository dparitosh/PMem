import React from 'react';
import OntologyMapper from '../Components/OntologyMapper';
import DataGridWidget from '../widgets/DataGridWidget';
import PageHeader from '../widgets/PageHeader';

const ontologyRows = [
  { concern: 'Namespace and prefix', purpose: 'Make ontology ownership and reuse explicit', output: 'Prefix registry and stable IRI' },
  { concern: 'STEP AP242 alignment', purpose: 'Map product instances to standard product semantics', output: 'Entity-to-class mappings' },
  { concern: 'Merge and harmonize', purpose: 'Reduce duplicate concepts across imported ontologies', output: 'Conflict report and merged model' },
  { concern: 'Dictionary generation', purpose: 'Expose classes, properties, and definitions for users', output: 'Data dictionary artifact' },
];

export default function OntologyStudioPage() {
  return (
    <div className="depo-page">
      <PageHeader
        eyebrow="Ontology studio"
        title="Govern the semantic model before linking product instances"
        summary="This page should answer whether a concept belongs in the enterprise ontology, how it maps to AP242 or other standards, and what vocabulary users can trust."
        insights={[
          { label: 'Model intent', value: 'Create reusable semantics, not one-off upload outputs' },
          { label: 'Alignment lens', value: 'AP242, AP239, MBSE, and enterprise vocabulary' },
          { label: 'Quality signal', value: 'Duplicate concepts and unmapped entities require review' },
        ]}
      />
      <DataGridWidget
        title="Ontology Work Areas"
        subtitle="Corporate ontology work separates namespace governance, standards mapping, merge control, and dictionary publishing."
        rows={ontologyRows}
        height={210}
        columns={[
          { field: 'concern', flex: 1 },
          { field: 'purpose', flex: 2 },
          { field: 'output', flex: 1.4 },
        ]}
      />
      <section className="depo-panel">
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Mapping and Alignment Workbench</div>
            <div className="depo-panel__meta">Map imported entities, review dictionaries, and align source terms to ontology classes.</div>
          </div>
        </div>
        <div className="depo-panel__body">
          <OntologyMapper />
        </div>
      </section>
    </div>
  );
}
