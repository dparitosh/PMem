import { inferFileTypeFromExtension } from './workflowEngine';

export const RESUMABLE_JOB_MAX_AGE_MS = 6 * 60 * 60 * 1000;
const ONTOLOGY_SOURCE_TYPES = new Set(['ontology', 'xsd', 'xmi', 'express']);
const ONTOLOGY_METADATA_EXTENSIONS = new Set(['.xsd', '.xmi', '.mdxml', '.owl', '.rdf', '.ttl', '.exp']);

export function serializeFileForPersistence(file) {
  if (!file) return null;
  const { fileObj, ...rest } = file;
  return { ...rest, fileObj: null, persisted: true };
}

export function getStatusTimestamp(status = {}, file = null) {
  return status.lastUpdatedAt || status.completedAtIso || file?.updatedAt || file?.createdAt || null;
}

export function isTerminalPipelineStatus(status = {}) {
  return ['failed', 'completed', 'awaitingReview'].includes(importJobState(status));
}

export function isResumablePersistedJob(file, status, now = Date.now()) {
  if (!file?.taskId || !status || isTerminalPipelineStatus(status)) return false;
  const parsed = Date.parse(getStatusTimestamp(status, file) || '');
  return !Number.isNaN(parsed) && (now - parsed) <= RESUMABLE_JOB_MAX_AGE_MS;
}

export function getFileExtensionFromName(fileName = '') {
  const parts = String(fileName).split('.');
  return parts.length > 1 ? `.${parts.pop().toLowerCase()}` : '';
}

export function isOntologySourceFile(fileName = '') {
  return ONTOLOGY_SOURCE_TYPES.has(inferFileTypeFromExtension(fileName));
}

export function requiresOntologyMetadataCapture(fileName = '') {
  return ONTOLOGY_METADATA_EXTENSIONS.has(getFileExtensionFromName(fileName));
}

export function getWorkflowNote({
  canRunSelectedWorkflow,
  fallbackWorkflow,
  mappingFileTypeContext,
  selectedWorkflow,
  selectedImportArtifactEntry,
}) {
  if (!canRunSelectedWorkflow) return `${fallbackWorkflow.title} is not connected yet.`;
  if (selectedWorkflow === 'instance.link') {
    return selectedImportArtifactEntry
      ? 'Review one imported instance artifact against one ontology, create a Bridge job preview, review candidate IDs, then publish approved mappings.'
      : 'Select one completed import artifact first, then choose the ontology you want to align against.';
  }
  if (selectedWorkflow === 'document.unstructured') return 'Add documents to extract content, prepare retrieval context and retain processing evidence.';
  if (selectedWorkflow === 'ontology.create') return 'Use this workflow only for ontology or schema registration. XSD, OWL, RDF, TTL, XMI, MDXML, and EXPRESS files belong here; instance files belong in Import instance graph.';
  if (selectedWorkflow === 'architecture.archimate') return 'Upload ArchiMate Model Exchange XML to create a process-reference architecture graph with typed relationships.';
  if (selectedWorkflow === 'ontology.merge') return 'Select a source ontology and a different target ontology, then review the merge plan.';
  if (['ontology.validate', 'dictionary.generate', 'taxonomy.generate', 'graph.chunk'].includes(selectedWorkflow)) return 'Select an ontology to generate the artifact.';
  if (mappingFileTypeContext === 'express') return 'EXPRESS creates ontology structure.';
  if (mappingFileTypeContext === 'step') return 'STEP validation retains a Data Flow run. Review its evidence in Data Flow and request release in Change Control. Validation alone does not publish data. After a publication receipt is retained, link the published instances to the AP242 ontology.';
  if (selectedWorkflow === 'instance.import' && ['csv', 'excel'].includes(mappingFileTypeContext)) return 'CSV and Excel import as source data first.';
  if (selectedWorkflow === 'instance.import' && ['json', 'xml', 'plmxml', 'reqif', '3dxml'].includes(mappingFileTypeContext)) return 'JSON, XML, PLMXML, ReqIF, and 3DXML import as source data first.';
  if (selectedWorkflow === 'instance.import' && ['ontology', 'xsd', 'xmi', 'express'].includes(mappingFileTypeContext)) return 'Use Create ontology for OWL, RDF, TTL, XSD, XMI, MDXML, or EXPRESS files.';
  if (selectedWorkflow === 'instance.import' && !mappingFileTypeContext) return 'Select files to continue.';
  return 'Ready.';
}


export function isAwaitingImportApproval(status = {}) {
  return status.status === 'ready_for_commit' && !status.committing && !status.error && !status.commitError;
}


// Persisted outcome takes precedence over the in-memory started set.
export function importJobState(status = {}, started = false) {
  if (status.error || status.commitError || status.resumeExpired || status.outcomeUnknown
      || status.stage === 'error' || status.commitPhase === 'error'
      || ['failed', 'error', 'outcome_unknown'].includes(status.status)) return 'failed';
  if (status.committed) return 'completed';
  if (isAwaitingImportApproval(status)) return 'awaitingReview';
  if (status.committing || status.status === 'committing') return 'active';
  if (status.status === 'completed' || status.commitPhase === 'complete') return 'completed';
  return started ? 'active' : 'pending';
}

export function governedSourceProfile(filename, sourceProfile = 'auto') {
  const extension = getFileExtensionFromName(filename).toLowerCase();
  const profiles = {
    '.stp': { profile: 'ap242-step-mbd', sourceSystem: 'CAD' },
    '.step': { profile: 'ap242-step-mbd', sourceSystem: 'CAD' },
    '.stpx': { profile: 'ap242-step-mbd', sourceSystem: 'CAD' },
    '.reqif': { profile: 'reqif', sourceSystem: 'Requirements management' },
    '.reqifz': { profile: 'reqif', sourceSystem: 'Requirements management' },
    '.xmi': { profile: 'sysml-v1', sourceSystem: 'MBSE' },
    '.mdxml': { profile: 'sysml-v1', sourceSystem: 'MBSE' },
    '.qif': { profile: 'qif', sourceSystem: 'Quality management' },
    '.plmxml': { profile: 'plmxml', sourceSystem: 'PLM' },
  };
  const explicit = {plmxml:{profile:'plmxml',sourceSystem:'PLM'},'sysml-v1':{profile:'sysml-v1',sourceSystem:'MBSE'},qif:{profile:'qif',sourceSystem:'Quality management'}};
  return extension === '.xml' && Object.hasOwn(explicit,sourceProfile) ? explicit[sourceProfile] : profiles[extension] || null;
}



export function selectSourceWorkflow(definitions, standard) {
  const candidates=(Array.isArray(definitions)?definitions:[]).filter(row=>row.job_id==='semantic-source-validation'&&row.job_type==='validate-semantic-batch'&&row.lifecycle_state==='approved'&&row.enabled===true&&Array.isArray(row.allowed_standards)&&row.allowed_standards.includes(standard)&&typeof row.version==='string'&&/^\d+\.\d+\.\d+$/.test(row.version));
  candidates.sort((left,right)=>{const a=left.version.split('.').map(Number),b=right.version.split('.').map(Number);return b[0]-a[0]||b[1]-a[1]||b[2]-a[2];});
  if(!candidates.length)throw new Error(`No approved engineering-source workflow supports ${standard}. Review source support in Change Control.`);
  return {job_id:candidates[0].job_id,version:candidates[0].version};
}
