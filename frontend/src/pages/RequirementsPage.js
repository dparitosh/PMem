import React from 'react';
import { RequirementsWorkbench } from '../Components/OntologyMapper';

export default function RequirementsPage({ onNavigate }) {
  return (
    <div className="depo-page">
      <RequirementsWorkbench onNavigate={onNavigate} />
    </div>
  );
}
