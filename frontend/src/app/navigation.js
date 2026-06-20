import {
  FileBarChart2,
  GitFork,
  Home,
  Network,
  Settings,
  Sparkles,
  UploadCloud,
} from 'lucide-react';

export const navigationItems = [
  { id: 'home', label: 'Home', icon: Home },
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
  table: 'graph',
  reports: 'reports',
  recommendations: 'quality',
  admin: 'admin',
  whereused: 'whereused',
  workspace: 'graph',
  import: 'import',
  quality: 'quality',
};

export function normalizePage(page) {
  return pageAliases[page] || page || 'graph';
}

export function pageLabel(page) {
  if (page === 'whereused') return 'Where Used';
  const item = navigationItems.find((nav) => nav.id === page);
  return item?.label || 'Graph Explorer';
}
