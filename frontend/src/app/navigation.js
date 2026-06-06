import {
  BarChart3,
  DatabaseZap,
  FileInput,
  Gauge,
  Network,
  PanelsTopLeft,
  Settings,
} from 'lucide-react';

export const navigationItems = [
  { id: 'workspace', label: 'Workspace', icon: PanelsTopLeft },
  { id: 'import', label: 'Import', icon: FileInput },
  { id: 'ontology', label: 'Ontology Studio', icon: DatabaseZap },
  { id: 'graph', label: 'Graph Explorer', icon: Network },
  { id: 'quality', label: 'Quality', icon: Gauge },
  { id: 'reports', label: 'Reports', icon: BarChart3 },
  { id: 'admin', label: 'Admin', icon: Settings },
];

export const pageAliases = {
  graph: 'graph',
  home: 'home',
  ingestion: 'import',
  ontology: 'ontology',
  table: 'workspace',
  reports: 'reports',
  recommendations: 'quality',
  admin: 'admin',
  whereused: 'whereused',
  workspace: 'workspace',
  import: 'import',
  quality: 'quality',
};

export function normalizePage(page) {
  return pageAliases[page] || page || 'workspace';
}

export function pageLabel(page) {
  if (page === 'whereused') return 'Where Used';
  const item = navigationItems.find((nav) => nav.id === page);
  return item?.label || 'Workspace';
}
