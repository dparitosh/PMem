import React, { useState } from 'react';
import WorkspaceTabs from '../Components/WorkspaceTabs';
import ImportWorkspace from "../features/import/ImportWorkspace.js";
import QifPage from './QifPage';
import SysmlRepositoryImport from './SysmlRepositoryImport';
import './ImportPage.css';

export default function ImportPage() {
  const [activeTab, setActiveTab] = useState('data');
  return (
    <div className="depo-page">
      <WorkspaceTabs label="Import workspaces" tabs={[{id:'data',label:'Data import'}, {id:'qif',label:'QIF workflow'}, {id:'sysml',label:'SysML repository'}]} value={activeTab} onChange={setActiveTab} />
      {activeTab === 'data' ? <ImportWorkspace /> : activeTab === 'qif' ? <QifPage workflowMode /> : <SysmlRepositoryImport />}
    </div>
  );
}
