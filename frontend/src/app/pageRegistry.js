import { lazy } from 'react';

// The route registry is the single source of truth for SPA page modules.
// Keeping imports lazy preserves a fast initial shell while each page remains
// independently owned and testable.
const ImportPage = lazy(() => import('../pages/ImportPage'));
const OntologyJunctionPage = lazy(() => import('../pages/OntologyJunctionPage'));
const MetadataRegistryPage = lazy(() => import('../pages/MetadataRegistryPage'));
const GraphExplorerPage = lazy(() => import('../pages/GraphExplorerPage'));
const CodeAuditPage = lazy(() => import('../pages/CodeAuditPage'));
const ModelWorkbenchPage = lazy(() => import('../pages/ModelWorkbenchPage'));
const RecommendationsPage = lazy(() => import('../pages/RecommendationsPage'));
const ReportsPage = lazy(() => import('../pages/ReportsPage'));
const AdminPage = lazy(() => import('../pages/AdminPage'));
const WhereUsedPage = lazy(() => import('../pages/WhereUsedPage'));
const RequirementsPage = lazy(() => import('../pages/RequirementsPage'));
const QifPage = lazy(() => import('../pages/QifPage'));

export const pageRegistry = {
  import: { component: ImportPage },
  ontology: { component: OntologyJunctionPage },
  registry: { component: MetadataRegistryPage },
  graph: { component: GraphExplorerPage, props: ({ graphProps }) => graphProps },
  'code-audit': { component: CodeAuditPage },
  modeling: { component: ModelWorkbenchPage, props: ({ onNavigate }) => ({ onNavigate }) },
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
