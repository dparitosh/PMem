import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';
import './CSS/TCSColors.css';
import Chatbot from './Components/Chatbot';
import ErrorBoundary from './Components/ErrorBoundary';
import LandingPage from './Components/LandingPage';
import { SchemaProvider } from './SchemaContext';
import { OntologyProvider } from './contexts/OntologyContext';
import { useCallback, useState } from 'react';
import AppShell from './app/AppShell';
import { normalizePage } from './app/navigation';
import WorkspacePage from './pages/WorkspacePage';
import ImportPage from './pages/ImportPage';
import OntologyStudioPage from './pages/OntologyStudioPage';
import GraphExplorerPage from './pages/GraphExplorerPage';
import QualityPage from './pages/QualityPage';
import ReportsPage from './pages/ReportsPage';
import AdminPage from './pages/AdminPage';
import WhereUsedPage from './pages/WhereUsedPage';

function App() {
  const [page, setPage] = useState('home');
  const [activePage, setActivePage] = useState('graph');
  const [data, setData] = useState();
  const [searchResults, setSearchResults] = useState(null);
  const [chatResults, setChatResults] = useState(null);
  const [showChat, setShowChat] = useState(false);
  const [visibleRelationships, setVisibleRelationships] = useState(null);

  const toggleChat = useCallback(() => {
    setShowChat((prev) => !prev);
    setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
  }, []);

  const handleNavigate = useCallback((target) => {
    const nextPage = normalizePage(target);
    if (nextPage === 'home') {
      setPage('home');
      return;
    }
    setPage('app');
    setActivePage(nextPage);
    setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
  }, []);

  const handleSchemaCleaned = useCallback(() => {
    setData({ nodes: [], links: [] });
    setSearchResults(null);
    setChatResults(null);
    setVisibleRelationships(null);
  }, []);

  const graphProps = {
    graphData: data,
    setData,
    searchResults,
    setSearchResults,
    chatResults,
    setChatResults,
    visibleRelationships,
    setVisibleRelationships,
    showChat,
    toggleChat,
    setActiveTab: handleNavigate,
  };

  const renderPage = () => {
    switch (activePage) {
      case 'workspace':
        return (
          <WorkspacePage
            data={data}
            searchResults={searchResults}
            chatResults={chatResults}
            visibleRelationships={visibleRelationships}
            onNavigate={handleNavigate}
          />
        );
      case 'import':
        return <ImportPage />;
      case 'ontology':
        return <OntologyStudioPage />;
      case 'quality':
        return <QualityPage setActiveTab={handleNavigate} />;
      case 'reports':
        return <ReportsPage searchResults={searchResults} chatResults={chatResults} graphData={data} />;
      case 'admin':
        return <AdminPage onSchemaCleaned={handleSchemaCleaned} />;
      case 'whereused':
        return <WhereUsedPage {...graphProps} data={data} />;
      case 'graph':
      default:
        return <GraphExplorerPage {...graphProps} />;
    }
  };

  if (page === 'home') {
    return (
      <ErrorBoundary>
        <OntologyProvider>
          <SchemaProvider>
            <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div style={{
                height: '8vh',
                backgroundColor: '#2c3e50',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                paddingLeft: 20,
                paddingRight: 20,
                boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
                flexShrink: 0,
              }}>
                <h1 style={{ color: 'white', margin: 0, fontSize: 20, fontWeight: 600 }}>
                  DEPO: Digital Engineering Product Ontology Knowledge Graph
                </h1>
                <button
                  onClick={() => handleNavigate('graph')}
                  style={{
                    background: 'rgba(255,255,255,0.15)',
                    color: '#fff',
                    border: '1px solid rgba(255,255,255,0.4)',
                    borderRadius: 6,
                    padding: '5px 16px',
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  Graph Explorer
                </button>
              </div>
              <div style={{ flex: '1 1 0', minHeight: 0 }}>
                <LandingPage setChatResults={setChatResults} onNavigate={handleNavigate} />
              </div>
            </div>
          </SchemaProvider>
        </OntologyProvider>
      </ErrorBoundary>
    );
  }

  return (
    <ErrorBoundary>
      <OntologyProvider>
        <SchemaProvider>
          <AppShell
            activePage={activePage}
            onPageChange={handleNavigate}
            onHome={() => setPage('home')}
            showChat={showChat}
            onToggleChat={toggleChat}
            rightDrawer={(
              <ErrorBoundary>
                <Chatbot
                  graphData={data}
                  searchResults={searchResults}
                  chatResults={chatResults}
                  setSearchResults={setSearchResults}
                  setChatResults={setChatResults}
                />
              </ErrorBoundary>
            )}
          >
            {renderPage()}
          </AppShell>
        </SchemaProvider>
      </OntologyProvider>
    </ErrorBoundary>
  );
}

export default App;
