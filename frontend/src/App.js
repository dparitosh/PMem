import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';
import './CSS/TCSColors.css';
import GraphHEB from "./Components/GraphHEB";
import Header from "./Components/Header";
import Chatbot from "./Components/Chatbot";
import TableView from './Components/TableView';
import ReportsTab from './Components/ReportsTab';
import WhereUsedView from './Components/WhereUsedView';
import RecommendationsTab from './Components/RecommendationsTab';
import OntologyMapper from './Components/OntologyMapper';
import DataImportPipeline from './Components/DataImportPipeline';
import TabContainer from './Components/TabContainer';
import ErrorBoundary from './Components/ErrorBoundary';
import ResizableSplitter from './Components/ResizableSplitter';
import { SchemaProvider } from './SchemaContext';
import { useState, useCallback } from 'react';

const MIDDLE_HEIGHT = () => window.innerHeight * 0.45;

function App() {
  const [data, setData] = useState();
  const [activeTab, setActiveTab] = useState('graph');
  const [searchResults, setSearchResults] = useState(null);
  const [chatResults, setChatResults] = useState(null);
  const [showChat, setShowChat] = useState(false);
  const [visibleRelationships, setVisibleRelationships] = useState(null);
  const [graphHeight, setGraphHeight] = useState(MIDDLE_HEIGHT());
  const [splitState, setSplitState] = useState('middle'); // 'up' | 'middle' | 'down'

  const toggleChat = () => {
    setShowChat(prev => !prev);
    setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
  };

  // Up = collapse graph, tabs take full space
  const handleClickUp = useCallback(() => {
    setGraphHeight(50);
    setSplitState('up');
    setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
  }, []);

  // Down = graph full, tabs collapse
  const handleClickDown = useCallback(() => {
    const container = document.querySelector('.cloud-main');
    const maxH = container ? container.getBoundingClientRect().height - 60 : window.innerHeight * 0.85;
    setGraphHeight(maxH);
    setSplitState('down');
    setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
  }, []);

  // Manual drag resets to 'middle' state
  const handleManualResize = useCallback((h) => {
    setGraphHeight(h);
    setSplitState('middle');
  }, []);

  // When a tab is selected from Tools menu, auto-expand tabs section
  const handleSetActiveTab = useCallback((tab) => {
    setActiveTab(tab);
    if (tab !== 'graph' && tab !== 'whereused' && splitState === 'down') {
      setGraphHeight(MIDDLE_HEIGHT());
      setSplitState('middle');
    }
    setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
  }, [splitState]);

  return (
    <ErrorBoundary>
      <SchemaProvider>
      <>
        <Header />
      <div id="cloud-container">
      
      {/* Where Used toolbar */}
      {activeTab === 'whereused' && (
        <div style={{ padding:'4px 10px' }}>
          <div style={{
            display:'flex',
            alignItems:'center',
            gap:'12px',
            background:'#ffffff',
            border:'1px solid #e2e6ea',
            borderRadius:'6px',
            padding:'6px 10px',
          }}>
            <button
              onClick={() => setActiveTab('graph')}
              style={{
                backgroundColor:'#004B87',
                color:'#fff',
                border:'none',
                padding:'4px 10px',
                borderRadius:'4px',
                fontWeight:600,
                cursor:'pointer',
                fontSize:'13px'
              }}
            >← Back to Graph</button>
            <div style={{ color:'#004B87', fontWeight:700, fontSize:'14px' }}>Where Used Analysis</div>
          </div>
        </div>
      )}
      
      {/* Main interactive area */}
  <div className={`cloud-main ${activeTab === 'whereused' ? 'whereused-wrapper' : ''}`}>        
        
        {activeTab === 'whereused' ? (
          <div className='p-0' id="whereused-container" style={{ position:'relative', width:'100%' }}>
            <ErrorBoundary>
              <WhereUsedView 
                data={data}
                setData={setData}
                searchResults={searchResults}
                setSearchResults={setSearchResults}
                chatResults={chatResults}
                setChatResults={setChatResults}
                visibleRelationships={visibleRelationships}
                setVisibleRelationships={setVisibleRelationships}
                setActiveTab={setActiveTab}
                showChat={showChat}
                toggleChat={toggleChat}
              />
            </ErrorBoundary>
          </div>
        ) : (
          <>
            {/* Graph section - resizable height */}
            <div 
              className='graph-section-container'
              style={{
                flex: `0 0 ${graphHeight}px`,
                overflow: 'hidden',
                borderBottom: '1px solid #e2e6ea',
              }}
            >
              <div style={{ display:'flex', margin: 0, padding: 0, height: '100%' }}>
                {/* Left column: Chat (conditional) */}
                {showChat && (
                  <div style={{ width:'280px', minWidth:'240px', height:'100%', borderRight:'1px solid #e2e6ea' }}>
                    <ErrorBoundary>
                      <Chatbot 
                        graphData={data} 
                        searchResults={searchResults} 
                        chatResults={chatResults}
                        setSearchResults={setSearchResults}
                        setChatResults={setChatResults}
                      />
                    </ErrorBoundary>
                  </div>
                )}
                {/* Right column: Graph visualization */}
                <div style={{ flex:1, height:'100%', minWidth:0 }} id="graph-container">
                  <ErrorBoundary>
                    <GraphHEB
                      graphData={data}
                      setData={setData}
                      searchResults={searchResults}
                      setSearchResults={setSearchResults}
                      chatResults={chatResults}
                      setChatResults={setChatResults}
                      visibleRelationships={visibleRelationships}
                      setVisibleRelationships={setVisibleRelationships}
                      showChat={showChat}
                      toggleChat={toggleChat}
                      setActiveTab={handleSetActiveTab}
                    />
                  </ErrorBoundary>
                </div>
              </div>
            </div>
            
            {/* Resizable divider */}
            <ResizableSplitter 
              onResize={handleManualResize} 
              graphHeight={graphHeight}
              splitState={splitState}
              onClickUp={handleClickUp}
              onClickDown={handleClickDown}
            />
            
            {/* Tabs section - fills remaining space */}
            <div 
              className='tabs-section-container'
              style={{
                flex: '1 1 auto',
                minHeight: 0,
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              {/* Tab navigation bar */}
              <div className="tab-nav-bar" style={{
                display: 'flex',
                alignItems: 'center',
                gap: '2px',
                padding: '4px 8px',
                background: '#f0f2f5',
                borderBottom: '2px solid #004B87',
                flexShrink: 0,
              }}>
                {[
                  { id: 'whereused', label: '↗ Where Used' },
                  { id: 'table', label: '▦ Table' },
                  { id: 'reports', label: '▲ Reports' },
                  { id: 'ingestion', label: '↓ Data Import' },
                  { id: 'ontology', label: '◆ Ontology Mapper' },
                  { id: 'recommendations', label: '★ Recommendations' },
                ].map(tab => (
                  <button
                    key={tab.id}
                    onClick={() => handleSetActiveTab(tab.id)}
                    style={{
                      padding: '6px 14px',
                      fontSize: '12px',
                      fontWeight: activeTab === tab.id ? 700 : 500,
                      border: 'none',
                      borderRadius: '6px 6px 0 0',
                      cursor: 'pointer',
                      background: activeTab === tab.id ? '#004B87' : 'transparent',
                      color: activeTab === tab.id ? '#fff' : '#333',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {/* Tab content area */}
              <div style={{ flex: '1 1 0', minHeight: 0, position: 'relative', overflow: 'hidden' }}>
                <TabContainer isActive={activeTab === 'table'} tabId="table">
                  <div className='table-wrapper' id="table-container" style={{ position:'absolute', inset:0, overflow:'auto', padding:'4px' }}>
                    <ErrorBoundary>
                      <TableView
                        data={data}
                        searchResults={searchResults}
                        chatResults={chatResults}
                        visibleRelationships={visibleRelationships}
                      />
                    </ErrorBoundary>
                  </div>
                </TabContainer>
                
                <TabContainer isActive={activeTab === 'reports'} tabId="reports">
                  <div className='reports-wrapper' id="reports-container" style={{ position:'absolute', inset:0, overflow:'auto', padding:'4px' }}>
                    <ErrorBoundary>
                      <ReportsTab 
                        searchResults={searchResults} 
                        chatResults={chatResults}
                        graphData={data}
                      />
                    </ErrorBoundary>
                  </div>
                </TabContainer>
                
                <TabContainer isActive={activeTab === 'ingestion'} tabId="ingestion">
                  <div id="ingestion-container" style={{ position:'absolute', inset:0, overflow:'auto', padding:'4px' }}>
                    <ErrorBoundary>
                      <DataImportPipeline />
                    </ErrorBoundary>
                  </div>
                </TabContainer>
                
                <TabContainer isActive={activeTab === 'recommendations'} tabId="recommendations">
                  <div id="recommendations-container" style={{ position:'absolute', inset:0, overflow:'auto', padding:'4px' }}>
                    <ErrorBoundary>
                      <RecommendationsTab setActiveTab={setActiveTab} />
                    </ErrorBoundary>
                  </div>
                </TabContainer>

                <TabContainer isActive={activeTab === 'ontology'} tabId="ontology">
                  <div id="ontology-container" style={{ position:'absolute', inset:0, overflow:'auto', padding:'4px' }}>
                    <ErrorBoundary>
                      <OntologyMapper />
                    </ErrorBoundary>
                  </div>
                </TabContainer>
              </div>
            </div>
          </>
        )}

      </div>
      </div>
    </>
      </SchemaProvider>
    </ErrorBoundary>
  );
}

export default App;
