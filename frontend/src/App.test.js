import { fireEvent, render, screen } from '@testing-library/react';
import App from './App';

jest.mock('./SchemaContext', () => ({
  SchemaProvider: ({ children }) => children,
}));

jest.mock('./contexts/OntologyContext', () => ({
  OntologyProvider: ({ children }) => children,
}));

jest.mock('./Components/LandingPage', () => () => <div>Landing Mock</div>);
jest.mock('./pages/ImportPage', () => () => <div data-testid="page-import">Import page</div>);
jest.mock('./pages/OntologyJunctionPage', () => () => <div data-testid="page-ontology">Ontology Junction page</div>);
jest.mock('./pages/MetadataRegistryPage', () => () => <div data-testid="page-registry">Metadata Registry page</div>);
jest.mock('./pages/GraphExplorerPage', () => () => <div data-testid="page-graph">Graph Explorer page</div>);
jest.mock('./pages/CodeAuditPage', () => () => <div data-testid="page-code-audit">Code Network page</div>);
jest.mock('./pages/ModelWorkbenchPage', () => () => <div data-testid="page-modeling">Modeling page</div>);
jest.mock('./pages/RecommendationsPage', () => () => <div data-testid="page-quality">Recommendations page</div>);
jest.mock('./pages/ReportsPage', () => () => <div data-testid="page-reports">Reports page</div>);
jest.mock('./pages/AdminPage', () => () => <div data-testid="page-admin">Admin page</div>);
jest.mock('./pages/WhereUsedPage', () => () => <div data-testid="page-whereused">Where Used page</div>);
jest.mock('./pages/RequirementsPage', () => () => <div data-testid="page-requirements">ReqIF page</div>);
jest.mock('./Components/Chatbot', () => () => <div data-testid="chatbot">Chatbot</div>);
jest.mock('./services/apiClient', () => ({
  API_METHODS: {
    health: {
      ready: jest.fn(() => Promise.resolve({ data: { status: 'ok' } })),
    },
  },
}));

beforeEach(() => {
  window.localStorage.clear();
  window.history.replaceState({}, '', '/');
});

test('renders DEPO platform landing page when home is persisted', () => {
  window.localStorage.setItem('depo.activePage', 'home');
  render(<App />);
  expect(screen.getByText(/DEPO Digital Thread Platform/i)).toBeInTheDocument();
});

test('renders the landing page for the root hash route', () => {
  window.history.replaceState({}, '', '/#/');
  render(<App />);
  expect(screen.getByText(/DEPO Digital Thread Platform/i)).toBeInTheDocument();
});

test('falls back to Graph Explorer for invalid persisted navigation', async () => {
  window.history.replaceState({}, '', '/#/graph');
  window.localStorage.setItem('depo.activePage', 'removed-page');
  render(<App />);
  expect(await screen.findByRole('heading', { name: 'Graph Explorer' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Graph Explorer' })).toHaveAttribute('aria-current', 'page');
});

test('routes every application navigation item to its page boundary', async () => {
  window.history.replaceState({}, '', '/#/graph');
  render(<App />);
  const routes = [
    ['Import', 'page-import'],
    ['Ontology Junction', 'page-ontology'],
    ['Metadata Registry', 'page-registry'],
    ['Code Network', 'page-code-audit'],
    ['Modeling', 'page-modeling'],
    ['ReqIF', 'page-requirements'],
    ['Where Used', 'page-whereused'],
    ['Recommendations', 'page-quality'],
    ['Reports', 'page-reports'],
    ['Admin', 'page-admin'],
    ['Graph Explorer', 'page-graph'],
  ];
  for (const [label, testId] of routes) {
    fireEvent.click(screen.getByRole('button', { name: label }));
    expect(await screen.findByTestId(testId)).toBeInTheDocument();
  }
});
