import {
  Boxes,
  FileBarChart2,
  FileText,
  GitFork,
  Home,
  LayoutDashboard,
  Network,
  Settings,
  Sparkles,
  UploadCloud,
} from 'lucide-react';

export const navigationItems = [
  { id: 'home', label: 'Home', icon: Home },
  { id: 'import', label: 'Import', icon: UploadCloud },
  { id: 'ontology', label: 'Ontology Junction', icon: Network },
  { id: 'graph', label: 'Graph Explorer', icon: GitFork },
  { id: 'modeling', label: 'Modeling', icon: LayoutDashboard },
  { id: 'requirements', label: 'ReqIF', icon: FileText },
  { id: 'whereused', label: 'Where Used', icon: Boxes },
  { id: 'quality', label: 'Recommendations', icon: Sparkles },
  { id: 'reports', label: 'Reports', icon: FileBarChart2 },
  { id: 'admin', label: 'Admin', icon: Settings },
];

export const pageAliases = {
  graph: 'graph',
  modeling: 'modeling',
  model: 'modeling',
  workbench: 'modeling',
  home: 'home',
  ingestion: 'import',
  ontology: 'ontology',
  table: 'graph',
  reports: 'reports',
  architecture: 'modeling',
  archimate: 'modeling',
  requirements: 'requirements',
  reqif: 'requirements',
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
