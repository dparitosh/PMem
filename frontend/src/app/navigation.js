import {
  FileBarChart2,
  GitFork,
  LayoutDashboard,
  Network,
  Settings,
  Sparkles,
  UploadCloud,
} from 'lucide-react';

export const navigationItems = [
  { id: 'workspace', label: 'Workspace', icon: LayoutDashboard },
  { id: 'import', label: 'Import', icon: UploadCloud },
  { id: 'ontology', label: 'Ontology Studio', icon: Network },
  { id: 'graph', label: 'Graph Explorer', icon: GitFork },
  { id: 'quality', label: 'Recommendations', icon: Sparkles },
  { id: 'reports', label: 'Reports', icon: FileBarChart2 },
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
