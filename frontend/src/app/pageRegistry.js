import { lazy } from 'react';
const moduleLoads = new Map();
function loadPage(name, importer) {
  if(!moduleLoads.has(name))moduleLoads.set(name,importer().catch(error=>{moduleLoads.delete(name);throw error;}));
  return moduleLoads.get(name);
}
const pageLoaders = {};
function lazyPage(name, importer) {
  pageLoaders[name]=()=>loadPage(name,importer);
  return lazy(pageLoaders[name]);
}
export function prefetchPage(name) {
  if(typeof navigator!=='undefined' && (navigator.connection?.saveData || /(^|-)2g$/.test(navigator.connection?.effectiveType||'')))return;
  const key=name==='catalog'?'data-products':name;
  pageLoaders[key]?.().catch(()=>{});
}


// The route registry is the single source of truth for SPA page modules.
// Keeping imports lazy preserves a fast initial shell while each page remains
// independently owned and testable.
const DataProductsPage = lazyPage('data-products', () => import('../pages/DataProductsPage'));
const ChangeControlPage = lazyPage('change-control', () => import('../pages/ChangeControlPage'));
const ImportPage = lazyPage('import', () => import('../pages/ImportPage'));
const DataFlowPage = lazyPage('data-flow', () => import('../pages/DataFlowPage'));
const OntologyJunctionPage = lazyPage('ontology', () => import('../pages/OntologyJunctionPage'));
const MetadataRegistryPage = lazyPage('registry', () => import('../pages/MetadataRegistryPage'));
const GraphExplorerPage = lazyPage('graph', () => import('../pages/GraphExplorerPage'));
const CodeAuditPage = lazyPage('code-audit', () => import('../pages/CodeAuditPage'));
const ModelWorkbenchPage = lazyPage('modeling', () => import('../pages/ModelWorkbenchPage'));
const QualityPage = lazyPage('data-quality', () => import('../pages/QualityPage'));
const RecommendationsPage = lazyPage('quality', () => import('../pages/RecommendationsPage'));
const ReportsPage = lazyPage('reports', () => import('../pages/ReportsPage'));
const AdminPage = lazyPage('admin', () => import('../pages/AdminPage'));
const WhereUsedPage = lazyPage('whereused', () => import('../pages/WhereUsedPage'));
const RequirementsPage = lazyPage('requirements', () => import('../pages/RequirementsPage'));
const QifPage = lazyPage('qif', () => import('../pages/QifPage'));

export const pageRegistry = {
  'change-control': {component:ChangeControlPage},
  'data-quality': { component: QualityPage },
  catalog: { component: DataProductsPage, props: () => ({ mode: 'catalog' }) },
  'data-products': { component: DataProductsPage },
  import: { component: ImportPage },
  'data-flow': { component: DataFlowPage },
  ontology: { component: OntologyJunctionPage, props: ({ onOntologyContextChange }) => ({ onCompanionContextChange:onOntologyContextChange }) },
  registry: { component: MetadataRegistryPage },
  graph: { component: GraphExplorerPage, props: ({ graphProps }) => graphProps },
  'code-audit': { component: CodeAuditPage },
  modeling: { component: ModelWorkbenchPage, props: ({ onNavigate, graphProps }) => ({ onNavigate, onBusinessSelection: graphProps?.onBusinessSelection, toggleChat: graphProps?.toggleChat }) },
  requirements: { component: RequirementsPage, props: ({ onNavigate }) => ({ onNavigate }) },
  qif: { component: QifPage },
  whereused: { component: WhereUsedPage, props: ({ graphProps, data }) => ({ ...graphProps, data }) },
  quality: { component: RecommendationsPage, props: ({ onNavigate }) => ({ setActiveTab: onNavigate }) },
  reports: { component: ReportsPage, props: ({ data, searchResults, chatResults }) => ({ graphData: data, searchResults, chatResults }) },
  admin: { component: AdminPage, props: ({ onSchemaCleaned }) => ({ onSchemaCleaned }) },
};

export function resolvePage(page) {
  return pageRegistry[page] || pageRegistry.graph;
}
