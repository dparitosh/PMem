import { agentToolResult } from './agentToolResult';
import agenticAPI from './agenticApi';
import { getCredentialProfile } from './serviceAuth';

export function validStewardReport(report) {
  const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  const count = value => Number.isSafeInteger(value) && value >= 0;
  if (!report || !['APPROVED','REJECTED','PENDING_VALIDATION'].includes(report.overall_verdict) ||
      !hash(report.audit_id) || !hash(report.policy_sha256) || !hash(report.artifact_sha256) ||
      !['imported_standard','enterprise_curated'].includes(report.profile) ||
      !['MAJOR','MINOR','PATCH','NONE'].includes(report.recommended_version_bump) ||
      !Array.isArray(report.violations_and_remediations) || report.violations_and_remediations.length > 200 ||
      !count(report.metrics?.findings) || !count(report.metrics?.quarantined_subjects) ||
      report.metrics.findings < report.violations_and_remediations.length ||
      typeof report.coverage?.complete !== 'boolean' ||
      report.violations_and_remediations.some(row => !row ||
        ['subject_uri','issue_category','diagnosis','action_taken'].some(key => typeof row[key] !== 'string' || !row[key]) ||
        !['BLOCKER','WARNING','EDITORIAL'].includes(row.severity) ||
        (row.recommended_action !== undefined && typeof row.recommended_action !== 'string'))) return false;
  return report.overall_verdict !== 'APPROVED' || (report.coverage.complete &&
    report.coverage.shacl === 'retained-result' && report.coverage.owl_rl_performed === true &&
    report.metrics.quarantined_subjects === 0 && !report.violations_and_remediations.some(row => row.severity === 'BLOCKER'));
}

async function execute(tool, inputs, approvedBy, agent = 'ontology-governor') {
  const actor = approvedBy.trim();
  const token = getCredentialProfile('AGENTIC_APPROVAL_TOKEN');
  if (!actor || !token) throw new Error('Enter the approving steward and connect governed agent access in Admin.');
  const response = await agenticAPI.runAgent(agent, tool, inputs,
    { approved_by: actor, approval_token: token });
  return agentToolResult(response, agent, tool);
}

export const ontologyMergeAgent = {
  evaluate: async (previewId, actor) => {
    const response = await execute('ontology.merge.evaluate', {preview_id: previewId}, actor, 'ontology-steward');
    const report = response.result.governance;
    if (response.result.preview_id !== previewId || !validStewardReport(report)) {
      throw new Error('Steward returned an incompatible governance report. Approval remains blocked.');
    }
    return response;
  },
  preview: (sources, options, actor) => execute('ontology.merge.preview', { source_ontology_ids: sources, ...options }, actor),
  apply: async (previewId, actor) => {
    const response = await execute('ontology.merge.apply', { preview_id: previewId, publish: true }, actor);
    const result = response.result;
    const ontologyId = result.ontology?.ontology_id;
    const publication = result.publication;
    const receipt = publication?.receipt;
    if (result.status === 'merged' && result.preview_id === previewId && ontologyId &&
        ['queued', 'running'].includes(result.publication_status) && publication?.status === result.publication_status &&
        publication.ontology_id === ontologyId && typeof publication.job_id === 'string' && publication.job_id) {
      return response;
    }
    if (result.status !== 'merged' || result.preview_id !== previewId || !ontologyId || result.publication_status !== 'published' ||
        publication?.status !== 'published' || publication.ontology_id !== ontologyId || !publication.publication_id ||
        receipt?.status !== 'published' || receipt.current !== true || receipt.ontology_id !== ontologyId || receipt.publication_id !== publication.publication_id ||
        ['resources','relationships'].some(field => !Number.isInteger(receipt[field]) || receipt[field] < 0) ||
        (publication.artifact_sha256 && publication.artifact_sha256 !== publication.publication_id)) {
      throw new Error('Merge publication receipt is unverified. Retry the same reviewed preview to reconcile its result.');
    }
    return response;
  },
};
