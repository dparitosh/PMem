import {
  BookOpen,
  Boxes,
  Database,
  FileCode2,
  GitMerge,
  Link2,
  ShieldCheck,
  Tags,
} from 'lucide-react';

export const pipelineStages = [
  { id: 'upload', label: 'Upload', description: 'File validation and format detection' },
  { id: 'convert', label: 'Convert', description: 'Parse to OWL2/Turtle' },
  { id: 'map', label: 'Map', description: 'Ontology alignment' },
  { id: 'validate', label: 'Validate', description: 'SHACL and quality check' },
  { id: 'enrich', label: 'Enrich', description: 'Semantic enrichment' },
  { id: 'load', label: 'Load', description: 'Ingest to Neo4j' },
  { id: 'verify', label: 'Verify', description: 'Post-load health check' },
];

export const backendToFrontendStage = {
  upload: 'upload',
  detect: 'upload',
  parse: 'convert',
  validate: 'validate',
  transform: 'validate',
  preview: 'validate',
  map: 'map',
  enrich: 'enrich',
  ingest: 'load',
  load: 'load',
  verify: 'verify',
};

export const supportedFormats = [
  { ext: '.csv', name: 'CSV' },
  { ext: '.json', name: 'JSON' },
  { ext: '.html', name: 'HTML' },
  { ext: '.htm', name: 'HTML' },
  { ext: '.owl', name: 'OWL' },
  { ext: '.rdf', name: 'RDF' },
  { ext: '.ttl', name: 'Turtle' },
  { ext: '.plmxml', name: 'PLMXML' },
  { ext: '.3dxml', name: '3DXML (3DEXPERIENCE)' },
  { ext: '.step', name: 'STEP' },
  { ext: '.stp', name: 'STEP' },
  { ext: '.stpx', name: 'STEP XML' },
  { ext: '.xls', name: 'Excel' },
  { ext: '.xlsx', name: 'Excel' },
  { ext: '.xmi', name: 'XMI' },
  { ext: '.mdxml', name: 'MagicDraw' },
  { ext: '.xml', name: 'XML' },
  { ext: '.xsd', name: 'XSD' },
  { ext: '.exp', name: 'EXPRESS' },
];

export const workflowCatalog = [
  {
    id: 'instance.import',
    label: 'Import instance graph',
    title: 'Import instance graph',
    category: 'Import',
    description: 'Parse product, tabular, or exchange files into inspectable instance entities, attributes, relationships, and metadata.',
    inputs: 'STEP, STPX, CSV, Excel, JSON, XML, PLMXML, 3DXML',
    outputs: ['Instance graph', 'Preview rows', 'Entity, attribute, relationship, and metadata counts'],
    status: 'available',
    execution: 'File upload',
    prerequisite: 'Choose one or more files',
    icon: Database,
    stages: ['Upload', 'Parse & preview', 'Structure check', 'Load & verify'],
    writes_to_neo4j: true,
    retains_artifacts: true,
  },
  {
    id: 'ontology.create',
    label: 'Create ontology',
    title: 'Create ontology',
    category: 'Ontology',
    description: 'Profile schema or ontology files, capture namespace and prefix metadata, preview the generated ontology, then register it.',
    inputs: 'EXPRESS, OWL, RDF, TTL, XSD, XMI, MDXML',
    outputs: ['Ontology preview', 'Prefix metadata', 'Schema classes'],
    status: 'available',
    execution: 'File upload',
    prerequisite: 'Choose an ontology/schema file',
    icon: FileCode2,
    stages: ['Upload schema file', 'Capture namespace and prefix', 'Generate ontology preview', 'Review and register ontology'],
    writes_to_neo4j: false,
    retains_artifacts: true,
  },
  {
    id: 'instance.link',
    label: 'Instance Alignment',
    title: 'Instance-to-Ontology Bridge',
    category: 'Mapping',
    description: 'Align imported instance data and metadata to ontology classes, data properties, object properties, and annotation properties. Use merge only for ontology-to-ontology consolidation.',
    inputs: 'One imported instance artifact plus one ontology',
    outputs: ['Entity-class mappings', 'Attribute-property mappings', 'Relationship-property mappings', 'Confidence and validation report'],
    status: 'available',
    execution: 'Artifact workflow',
    prerequisite: 'Run an import first, then select the instance artifact and ontology',
    icon: Link2,
    stages: ['Select imported instance', 'Select ontology', 'Preview semantic mappings', 'Review and apply'],
    writes_to_neo4j: true,
    retains_artifacts: true,
  },
  {
    id: 'ontology.merge',
    label: 'Merge ontologies',
    title: 'Merge ontologies',
    category: 'Ontology',
    description: 'Compare two ontologies and produce a merge plan. Source ontology and target ontology are selected explicitly, then the merge can be reviewed and committed.',
    inputs: 'Two ontology catalog entries',
    outputs: ['Merge plan', 'Overlap report', 'Addition candidates', 'Neo4j merge commit'],
    status: 'available',
    execution: 'Artifact workflow',
    prerequisite: 'Select source and target ontologies',
    icon: GitMerge,
    stages: ['Select sources', 'Detect overlaps', 'Identify additions', 'Export merge plan'],
    writes_to_neo4j: false,
    retains_artifacts: true,
  },
  {
    id: 'ontology.validate',
    label: 'Validate ontology',
    title: 'Validate ontology',
    category: 'Quality',
    description: 'Run quality, namespace, prefix, and consistency checks before publishing.',
    inputs: 'Ontology catalog entry or file',
    outputs: ['Validation report', 'Finding counts', 'Review suggestions'],
    status: 'available',
    execution: 'Artifact workflow',
    prerequisite: 'Select ontology',
    icon: ShieldCheck,
    stages: ['Select ontology', 'Run checks', 'Review findings', 'Export report'],
    writes_to_neo4j: false,
    retains_artifacts: true,
  },
  {
    id: 'dictionary.generate',
    label: 'Build data dictionary',
    title: 'Build data dictionary',
    category: 'Governance',
    description: 'Extract terms, fields, definitions, and source lineage for business review.',
    inputs: 'Ontology, graph, CSV, Excel',
    outputs: ['Data dictionary', 'Term lineage', 'Review queue'],
    status: 'available',
    execution: 'Artifact workflow',
    prerequisite: 'Select ontology',
    icon: BookOpen,
    stages: ['Select source', 'Extract terms', 'Review definitions', 'Publish dictionary'],
    writes_to_neo4j: false,
    retains_artifacts: true,
  },
  {
    id: 'taxonomy.generate',
    label: 'Build taxonomy',
    title: 'Build taxonomy',
    category: 'Ontology',
    description: 'Generate hierarchy, synonyms, and preferred terms from semantic assets.',
    inputs: 'Ontology or graph',
    outputs: ['Taxonomy tree', 'Synonym set', 'Rejected terms'],
    status: 'available',
    execution: 'Artifact workflow',
    prerequisite: 'Select ontology',
    icon: Tags,
    stages: ['Select source', 'Cluster concepts', 'Review hierarchy', 'Export taxonomy'],
    writes_to_neo4j: false,
    retains_artifacts: true,
  },
  {
    id: 'graph.chunk',
    label: 'Chunk and index graph',
    title: 'Chunk and index graph',
    category: 'Graph',
    description: 'Prepare ontology or graph chunks for search, retrieval, and downstream AI workflows.',
    inputs: 'Ontology or graph',
    outputs: ['Chunk set', 'Index manifest', 'Coverage report'],
    status: 'available',
    execution: 'Artifact workflow',
    prerequisite: 'Select ontology',
    icon: Boxes,
    stages: ['Select source', 'Choose chunking rule', 'Preview chunks', 'Export manifest'],
    writes_to_neo4j: false,
    retains_artifacts: true,
  },
];

export const executableWorkflowIds = workflowCatalog.map(workflow => workflow.id);

const normalizeWorkflowStatus = (status) => {
  if (['available', 'existing_import_pipeline', 'existing_upload_pipeline', 'artifact_report'].includes(status)) {
    return 'available';
  }
  return status || 'planned';
};

export const mergeWorkflowRuntimeOptions = (catalog, runtimeOptions = []) => {
  const runtimeById = new Map((runtimeOptions || []).map((option) => [option.id, option]));
  return (catalog || []).map((workflow) => {
    const runtime = runtimeById.get(workflow.id);
    if (!runtime) return workflow;
    return {
      ...workflow,
      status: normalizeWorkflowStatus(runtime.status || workflow.status),
      runtimeStatus: runtime.status || workflow.status,
      label: runtime.label || runtime.title || workflow.label,
      title: runtime.label || runtime.title || workflow.title,
      category: runtime.category || workflow.category,
      execution_surface: runtime.execution_surface || workflow.execution_surface,
      execution: runtime.execution || workflow.execution,
      prerequisite: runtime.prerequisite || workflow.prerequisite,
    };
  });
};

export const getWorkflowById = (workflowId) =>
  workflowCatalog.find(workflow => workflow.id === workflowId) || null;

export const getWorkflowMap = () =>
  Object.fromEntries(workflowCatalog.map(workflow => [workflow.id, workflow]));

export const resolveWorkflow = (workflowId, fallback = null) => {
  const lookup = getWorkflowById(workflowId);
  if (lookup) return lookup;
  return fallback;
};

export const getWorkflowDisplayName = (workflowId) => {
  const workflow = getWorkflowById(workflowId);
  return workflow?.title || workflow?.label || String(workflowId || 'Selected workflow');
};

export const isImportWorkflow = (workflowId) =>
  workflowId === 'instance.import' || workflowId === 'ontology.create';

export const getFileExtension = (fileName) =>
  `.${String(fileName || '').split('.').pop().toLowerCase()}`;

export const inferFileTypeFromExtension = (fileName) => {
  const ext = getFileExtension(fileName);
  if (['.stp', '.step', '.stpx'].includes(ext)) return 'step';
  if (['.csv'].includes(ext)) return 'csv';
  if (['.xls', '.xlsx'].includes(ext)) return 'excel';
  if (['.json'].includes(ext)) return 'json';
  if (['.3dxml'].includes(ext)) return '3dxml';
  if (['.xml'].includes(ext)) return 'xml';
  if (['.owl', '.rdf', '.ttl'].includes(ext)) return 'ontology';
  if (['.plmxml'].includes(ext)) return 'plmxml';
  if (['.xmi', '.mdxml'].includes(ext)) return 'xmi';
  if (['.xsd'].includes(ext)) return 'xsd';
  if (['.exp'].includes(ext)) return 'express';
  return '';
};

export const recommendWorkflowForFile = (fileName) => {
  const fileType = inferFileTypeFromExtension(fileName);
  if (['ontology', 'xsd', 'xmi', 'express'].includes(fileType)) return 'ontology.create';
  return 'instance.import';
};

const toWorkflowStageId = (workflowId, stage, idx) =>
  `${workflowId}-${idx}-${String(stage).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')}`;

export const buildWorkflowStages = (workflow) =>
  (workflow?.stages || []).map((stage, idx) => ({
    id: toWorkflowStageId(workflow.id, stage, idx),
    label: stage,
    description: idx === 0
      ? workflow.inputs
      : idx === (workflow.stages.length - 1)
        ? workflow.outputs.join(', ')
        : workflow.description,
    backendIds: workflow.id === 'instance.import'
      ? [
          ['upload', 'detect'],
          ['parse', 'convert', 'preview'],
          ['map', 'validate', 'transform', 'enrich'],
          ['ingest', 'load', 'verify'],
        ][idx] || []
      : workflow.id === 'ontology.create'
        ? [
            ['upload'],
            ['detect', 'parse'],
            ['preview', 'validate'],
            ['verify', 'load', 'completed'],
          ][idx] || []
        : [],
  }));

export const getStageLabel = (stageId) =>
  pipelineStages.find(stage => stage.id === stageId)?.label || stageId;
