import { ixIconName } from '../ui/ixIconRegistry';

export const navigationItems = [
  { id: 'home', label: 'Home', icon: ixIconName.home },
  { id: 'import', label: 'Import', icon: ixIconName.cloudUpload },
  { id: 'change-control', label: 'Change Control', icon: ixIconName.refreshSettings },
  { id: 'data-flow', label: 'Data Flow', icon: ixIconName.gauge },
  { id: 'ontology', label: 'Models & Vocabularies', icon: ixIconName.assetNetwork },
  { id: 'catalog', label: 'Data Catalog', icon: ixIconName.database },
  { id: 'data-products', label: 'Data Products', icon: ixIconName.networkDevice },
  { id: 'registry', label: 'Data Dictionary', icon: ixIconName.tagEye },
  { id: 'graph', label: 'Graph Explorer', icon: ixIconName.graph },
  { id: 'code-audit', label: 'Code Dependencies', icon: ixIconName.code },
  { id: 'modeling', label: 'Modeling', icon: ixIconName.chartDiagram },
  { id: 'requirements', label: 'ReqIF', icon: ixIconName.documentReference },
  { id: 'qif', label: 'QIF', icon: ixIconName.processControl },
  { id: 'whereused', label: 'Where Used', icon: ixIconName.listGraphics },
  { id: 'data-quality', label: 'Data Quality', icon: ixIconName.auditReport },
  { id: 'recommendations', label: 'Recommendations', icon: ixIconName.shieldCheck },
  { id: 'reports', label: 'Reports', icon: ixIconName.documentCode },
  { id: 'admin', label: 'Admin', icon: ixIconName.projectSettings },
];

export const pageAliases = {
  'change-control': 'change-control',
  changes: 'change-control',
  'data-quality': 'data-quality',
  catalog: 'catalog',
  'data-catalog': 'catalog',
  'data-products': 'data-products',
  products: 'data-products',
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
  recommendations: 'recommendations',
  quality: 'recommendations',
  admin: 'admin',
  whereused: 'whereused',
  workspace: 'graph',
  import: 'import',
  'data-flow': 'data-flow',
  dataflow: 'data-flow',
  pipeline: 'data-flow',
};

export const navigationGroups = [
  {label:'Ingest', pages:['import','data-flow']},
  {label:'Model', pages:['ontology','registry','modeling','requirements','qif']},
  {label:'Explore', pages:['graph','catalog','data-products','whereused','code-audit']},
  {label:'Decide', pages:['quality','change-control','data-quality','reports']},
  {label:'Administer', pages:['admin']},
].map(group=>({...group,items:group.pages.map(id=>navigationItems.find(item=>item.id===(pageAliases[id]||id)))}));

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
