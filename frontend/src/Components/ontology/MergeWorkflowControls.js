import React from 'react';
import './MergeMappingReview.css';

export default function MergeWorkflowControls({ availableCount = 2, sourceId, targetId, reviewer, onReviewerChange, connected,
  busy, preview, dirty, ready, publication, error, stewardStatus, selectionCount, onGenerate, onResume, children, showStatus = true }) {
  const sourcesReady = Boolean(sourceId && targetId && sourceId !== targetId);
  const accessReady = Boolean(reviewer.trim() && connected);
  const publishing = ['queued', 'running', 'published'].includes(publication);
  const pending = !dirty && preview?.background_validation && ['queued', 'preparing', 'validating'].includes(preview.job_status);
  const logicalCheckIncomplete = !pending && preview?.owl_dl_evidence?.status === 'unknown';
  const status = !sourcesReady ? 'Choose two ontology versions' : publication === 'published' ? 'Published to knowledge graph' : publishing ? 'Publication in progress'
    : busy ? 'Submitting request' : error ? 'Request needs attention' : dirty ? 'Mapping selection changed'
      : preview?.job_status === 'failed' ? 'Validation failed'
        : pending ? preview.job_status === 'validating' ? 'Validating semantic constraints' : 'Preparing mapping candidates'
          : logicalCheckIncomplete ? 'Logical consistency check incomplete' : stewardStatus === 'running' ? 'Ontology Steward is reviewing the plan' : stewardStatus === 'failed' ? 'Steward review needs attention' : ready ? 'Plan ready for your review' : preview ? 'Plan needs attention' : 'Ready to generate a plan';
  return <section className="merge-workflow" aria-label="Merge workflow controls">
    {showStatus && <div className="merge-agent-status" role="status" aria-live="polite"><strong>{status}</strong>{error && <p role="alert">{error}</p>}</div>}
    <div className="merge-action-row">
      <label htmlFor="merge-reviewer">Reviewer name
        <input id="merge-reviewer" value={reviewer} onChange={event => onReviewerChange(event.target.value)} placeholder="Your name or team identifier" />

      </label>
      <button type="button" className="merge-primary" disabled={busy || pending || publishing || !sourcesReady || !accessReady} onClick={onGenerate}>
        {pending ? 'Validation running' : dirty ? 'Validate selected mappings' : preview ? 'Regenerate mapping plan' : 'Generate mapping plan'}
      </button>
      <button type="button" disabled={busy || publishing || !sourcesReady} onClick={onResume}>Resume saved plan</button>
    </div>
    {availableCount < 2 && <a href="#/import">Import ontology versions</a>}
    {!connected && <a href="#/admin">Connect agent access in Admin</a>}
    {children}
    {preview?.preview_id && <a className="bridge-action" href={`#/change-control?source=merges&view=workflows&record_source=merges&record=${encodeURIComponent(preview.preview_id)}&return_to=${encodeURIComponent(`#/ontology?view=alignment&mode=merge&merge_source=${encodeURIComponent(sourceId)}&target=${encodeURIComponent(targetId)}&merge_preview=${encodeURIComponent(preview.preview_id)}`)}`}>Review CR / CO</a>}

  </section>;
}
