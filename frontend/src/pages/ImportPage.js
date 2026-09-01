import React, { useState } from 'react';
import DataImportPipeline from '../Components/DataImportPipeline';
import QifPage from './QifPage';
import './ImportPage.css';

export default function ImportPage() {
  const [activeTab, setActiveTab] = useState('data');
  return (
    <div className="depo-page">
      <div className="import-page-tabs" role="tablist" aria-label="Import workspaces">
        <button type="button" role="tab" aria-selected={activeTab === 'data'} onClick={() => setActiveTab('data')}>Data import</button>
        <button type="button" role="tab" aria-selected={activeTab === 'qif'} onClick={() => setActiveTab('qif')}>QIF workflow</button>
      </div>
      {activeTab === 'data' ? <DataImportPipeline /> : <QifPage workflowMode />}
    </div>
  );
}
