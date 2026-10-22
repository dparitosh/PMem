import React from 'react';
import './MergeMappingReview.css';

export default function MergeWorkflowControls({ availableCount = 2, sourceId, targetId, reviewer, onReviewerChange, connected,
  busy, preview, dirty, ready, publication, error, stewardStatus, selectionCount, onGenerate, onResume, onPublish }) {
  const sourcesReady = Boolean(sourceId && targetId && sourceId !== targetId);
  const accessReady = Boolean(reviewer.trim() && connected);
  const publishing = ['queued', 'running', 'published'].includes(publication);
  const pending = !dirty && preview?.background_validation && ['queued', 'preparing', 'validating'].includes(preview.job_status);
  const status = !sourcesReady ? 'Choose two ontology versions' : publication === 'published' ? 'Published to Neo4j' : publishing ? 'Publication in progress'
    : busy ? 'Submitting request' : error ? 'Request needs attention' : dirty ? 'Mapping selection changed'
      : preview?.job_status === 'failed' ? 'Validation failed'
        : pending ? preview.job_status === 'validating' ? 'Validating semantic constraints' : 'Preparing mapping candidates'
          : stewardStatus === 'running' ? 'Ontology Steward is reviewing the plan' : stewardStatus === 'failed' ? 'Steward review needs attention' : ready ? 'Plan ready for your review' : preview ? 'Plan needs attention' : 'Ready to generate a plan';
  const guidance = availableCount < 2 ? 'Register at least two ontology versions before generating a merge plan.' : !sourcesReady ? 'Choose two different ontology versions above.'
    : !connected ? 'Connect governed agent access in Admin to run the merge tools.'
      : !reviewer.trim() ? 'Enter the reviewing steward so the plan has an accountable identity.'
        : publication === 'published' ? 'Publication is confirmed. Review the publication receipt below.'
          : publishing ? 'Follow the publication status below; do not start another publication.'
            : busy ? 'Wait for the request receipt. No additional click is needed.'
              : error ? error
              : dirty ? 'Your selections are retained. Validate them to generate a current plan; approval is blocked until then.'
                : pending ? 'Candidates appear as preparation completes. Validation continues on the server; you can return using Resume saved plan.'
                  : stewardStatus === 'running' ? 'The existing Steward is evaluating the saved Governor plan. Publication remains blocked until its report is available.'
                  : ready ? `Review the proposed changes below. Approval creates and publishes a new ontology with ${selectionCount} identity consolidations.`
                    : preview ? 'Inspect the validation findings below. Resolve blocking issues before approval.'
                      : 'Generate a plan to see proposed mappings. This first action does not publish to Neo4j.';
  return <section className="merge-workflow" aria-label="Merge workflow controls">
    <ol className="merge-stages" aria-label="Merge progress">
      <li aria-current={!preview ? 'step' : undefined}><strong>1. Generate plan</strong><span>Governor runs matching tools</span></li>
      <li aria-current={preview && !publishing ? 'step' : undefined}><strong>2. Review mappings</strong><span>Steward audits; you review</span></li>
      <li aria-current={publishing ? 'step' : undefined}><strong>3. Approve and publish</strong><span>Governor submits to Neo4j</span></li>
    </ol>
    <div className="merge-agent-status" role="status" aria-live="polite"><strong>{status}</strong><p>{guidance}</p></div>
    <div className="merge-action-row">
      <label htmlFor="merge-reviewer">Reviewing steward
        <input id="merge-reviewer" value={reviewer} onChange={event => onReviewerChange(event.target.value)} placeholder="name or service principal" />
      </label>
      <button type="button" className="merge-primary" disabled={busy || pending || publishing || !sourcesReady || !accessReady} onClick={onGenerate}>
        {pending ? 'Validation running' : dirty ? 'Validate selected mappings' : preview ? 'Regenerate mapping plan' : 'Generate mapping plan'}
      </button>
      <button type="button" disabled={busy || publishing || !sourcesReady} onClick={onResume}>Resume saved plan</button>
      <button type="button" className="merge-publish" disabled={busy || publishing || dirty || !ready || !sourcesReady || !accessReady} onClick={onPublish}>Approve merge and publish</button>
    </div>
    {availableCount < 2 && <a href="#/import">Import ontology versions</a>}
    {!connected && <a href="#/admin">Connect agent access in Admin</a>}
    <details className="merge-method"><summary>What does the agent do, and what do I decide?</summary>
      <p>The Ontology Governor calls the registered matching and merge tools, retains the plan and runs semantic validation. Matching compares labels, character trigrams, definitions and property context. Similarity is evidence to review, not proof that two concepts are identical.</p>
      <p>You choose any identities to consolidate and approve the validated plan. With no pairs selected, the merge combines both vocabularies while preserving their distinct identities. Publication creates a new ontology; it does not replace either source.</p>
      <p>SHACL and OWL-RL checks provide structural evidence. They do not establish full OWL-DL consistency or business equivalence.</p>
    </details>
  </section>;
}
