import React from 'react';
import OntologyWorkspace from "../features/ontology/OntologyWorkspace.js";

export default function OntologyJunctionPage({onCompanionContextChange}) {
  return (
    <div className="depo-page depo-ontology-workspace">
      <OntologyWorkspace onCompanionContextChange={onCompanionContextChange} />
    </div>
  );
}
