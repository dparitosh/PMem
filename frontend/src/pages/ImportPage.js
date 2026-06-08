import React from 'react';
import DataImportPipeline from '../Components/DataImportPipeline';

export default function ImportPage() {
  return (
    <div className="depo-page">
      <section className="depo-panel">
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Pipeline</div>
            <div className="depo-panel__meta">Upload, preview, map, commit, and retain artifacts from one controlled surface.</div>
          </div>
        </div>
        <div className="depo-panel__body">
          <DataImportPipeline />
        </div>
      </section>
    </div>
  );
}
