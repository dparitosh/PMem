import React from 'react';
import RequirementsWorkbench from '../features/traceability/RequirementsWorkbench';

export default function RequirementsPage({ onNavigate }) {
  return (
    <div className="depo-page">
      <RequirementsWorkbench onNavigate={onNavigate} />
    </div>
  );
}
