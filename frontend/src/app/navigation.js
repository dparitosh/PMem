import { ixIconName } from '../ui/ixIconRegistry';

export const navigationItems = [
  { id: 'home', label: 'Home', icon: ixIconName.home },
  { id: 'import', label: 'Import', icon: ixIconName.cloudUpload },
  { id: 'data-flow', label: 'Data Flow', icon: ixIconName.gauge },
  { id: 'ontology', label: 'Ontology Junction', icon: ixIconName.assetNetwork },
  { id: 'registry', label: 'Metadata Registry', icon: ixIconName.database },
  { id: 'graph', label: 'Graph Explorer', icon: ixIconName.graph },
  { id: 'code-audit', label: 'Code Network', icon: ixIconName.code },
  { id: 'modeling', label: 'Modeling', icon: ixIconName.chartDiagram },
  { id: 'requirements', label: 'ReqIF', icon: ixIconName.documentReference },
  { id: 'qif', label: 'QIF', icon: ixIconName.processControl },
  { id: 'whereused', label: 'Where Used', icon: ixIconName.listGraphics },
  { id: 'quality', label: 'Recommendations', icon: ixIconName.auditReport },
  { id: 'reports', label: 'Reports', icon: ixIconName.documentCode },
  { id: 'admin', label: 'Admin', icon: ixIconName.projectSettings },
];

export const pageAliases = {
  graph: 'graph',
  'code-audit': 'code-audit',
  code: 'code-audit',
  modeling: 'modeling',
  model: 'modeling',
  workbench: 'modeling',
  home: 'home',
  ingestion: 'import',
  ontology: 'ontology',
  registry: 'registry',
  metadata: 'registry',
  'metadata-registry': 'registry',
  table: 'graph',
  reports: 'reports',
  architecture: 'modeling',
  archimate: 'modeling',
  requirements: 'requirements',
  reqif: 'requirements',
  qif: 'qif',
  recommendations: 'quality',
  admin: 'admin',
  whereused: 'whereused',
  workspace: 'graph',
  import: 'import',
  'data-flow': 'data-flow',
  dataflow: 'data-flow',
  pipeline: 'data-flow',
  quality: 'quality',
};

export function normalizePage(page) {
  if (typeof page !== 'string') return 'graph';
  const candidate = page.trim().toLowerCase();
  return pageAliases[candidate] || 'graph';
}

export function pageLabel(page) {
  if (page === 'whereused') return 'Where Used';
  const item = navigationItems.find((nav) => nav.id === page);
  return item?.label || 'Graph Explorer';
}
