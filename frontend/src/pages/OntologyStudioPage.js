import React from 'react';
import OntologyMapper from '../Components/OntologyMapper';

export default function OntologyStudioPage() {
  return (
    <div className="depo-page">
      <section className="depo-panel">
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Workbench</div>
            <div className="depo-panel__meta">Review ontology terms, mapping vocabulary, and alignment decisions in one workspace.</div>
          </div>
        </div>
        <div className="depo-panel__body">
          <OntologyMapper />
        </div>
      </section>
    </div>
  );
}
