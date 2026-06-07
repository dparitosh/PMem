import React from 'react';
import { CheckCircle2, Database, FileInput, Workflow } from 'lucide-react';
import { widgetCardStyle, widgetColors } from './widgetStyles';

const iconByCategory = {
  Import: FileInput,
  Mapping: Workflow,
  Ontology: Workflow,
  Quality: CheckCircle2,
  Governance: Database,
  Reports: FileInput,
};

export default function WorkflowWidget({ workflow, onOpen }) {
  const Icon = iconByCategory[workflow?.category] || Workflow;
  return (
    <button
      type="button"
      onClick={() => onOpen && onOpen(workflow)}
      style={{
        ...widgetCardStyle,
        textAlign: 'left',
        padding: 8,
        cursor: onOpen ? 'pointer' : 'default',
        minHeight: 86,
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Icon size={8} color={widgetColors.blue} strokeWidth={3.2} />
        <div style={{ color: widgetColors.text, fontSize: 12, fontWeight: 850, lineHeight: 1.25 }}>
          {workflow?.label}
        </div>
      </div>
      <div style={{ color: widgetColors.muted, fontSize: 10, lineHeight: 1.3 }}>
        <strong>Input:</strong> {workflow?.inputs}
      </div>
      <div style={{ color: widgetColors.muted, fontSize: 10, lineHeight: 1.3 }}>
        <strong>Output:</strong> {workflow?.outputs}
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 'auto' }}>
        <span style={{ fontSize: 9, fontWeight: 850, color: widgetColors.blue, background: '#eef5fb', padding: '2px 5px', borderRadius: 4 }}>
          {workflow?.category}
        </span>
        {workflow?.retains_artifacts && (
          <span style={{ fontSize: 9, fontWeight: 850, color: widgetColors.ok, background: '#edf9f2', padding: '2px 5px', borderRadius: 4 }}>
            Retains artifacts
          </span>
        )}
      </div>
    </button>
  );
}
