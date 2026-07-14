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
  return Boolean(
    status.error
    || status.status === 'failed'
    || status.status === 'ready_for_commit'
    || status.committed
    || status.status === 'completed'
    || status.commitPhase === 'complete'
    || status.progress === 100
  );
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
      ? 'Review one imported instance artifact against one ontology, then preview or apply semantic mappings.'
      : 'Select one completed import artifact first, then choose the ontology you want to align against.';
  }
  if (selectedWorkflow === 'ontology.create') return 'Use this workflow only for ontology or schema registration. XSD, OWL, RDF, TTL, XMI, MDXML, and EXPRESS files belong here; instance files belong in Import instance graph.';
  if (selectedWorkflow === 'architecture.archimate') return 'Upload ArchiMate Model Exchange XML to create a process-reference architecture graph with typed relationships.';
  if (selectedWorkflow === 'ontology.merge') return 'Select a source ontology and a different target ontology, then review the merge plan.';
  if (['ontology.validate', 'dictionary.generate', 'taxonomy.generate', 'graph.chunk'].includes(selectedWorkflow)) return 'Select an ontology to generate the artifact.';
  if (mappingFileTypeContext === 'express') return 'EXPRESS creates ontology structure.';
  if (mappingFileTypeContext === 'step') return 'STEP imports structural CAD instance data first. After commit, run Link instances to ontology with AP242 MBD/3D selected to create semantic INSTANCE_OF links.';
  if (selectedWorkflow === 'instance.import' && ['csv', 'excel'].includes(mappingFileTypeContext)) return 'CSV and Excel import as source data first.';
  if (selectedWorkflow === 'instance.import' && ['json', 'xml', 'plmxml', 'reqif', '3dxml'].includes(mappingFileTypeContext)) return 'JSON, XML, PLMXML, ReqIF, and 3DXML import as source data first.';
  if (selectedWorkflow === 'instance.import' && ['ontology', 'xsd', 'xmi', 'express'].includes(mappingFileTypeContext)) return 'Use Create ontology for OWL, RDF, TTL, XSD, XMI, MDXML, or EXPRESS files.';
  if (selectedWorkflow === 'instance.import' && !mappingFileTypeContext) return 'Select files to continue.';
  return 'Ready.';
}
