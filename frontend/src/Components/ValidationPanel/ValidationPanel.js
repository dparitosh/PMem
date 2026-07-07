import React from 'react';

export default function ValidationPanel({ validation }) {
  const issues = validation?.issues || [];
  return <aside className="validation-panel"><h3>Validation</h3>{issues.length === 0 ? <p>No issues.</p> : <ul>{issues.map((issue, index) => <li key={`${issue.rule}-${index}`} data-severity={issue.severity}>{issue.message}</li>)}</ul>}</aside>;
}
