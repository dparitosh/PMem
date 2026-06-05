import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';
import 'bootstrap/dist/css/bootstrap.css';
import GraphHEB from "./Components/GraphHEB";
import Header from "./Components/Header";
import Chatbot from "./Components/Chatbot";
import TableView from './Components/TableView';
import ReportsTab from './Components/ReportsTab';
import WhereUsedView from './Components/WhereUsedView';
import { SchemaProvider } from './SchemaContext';
import { useState } from 'react';

function App() {
  const [data, setData] = useState();
  const [activeTab, setActiveTab] = useState('graph');
  const [searchResults, setSearchResults] = useState(null);
  const [chatResults, setChatResults] = useState(null);
  const [showChat, setShowChat] = useState(false);
  const [visibleRelationships, setVisibleRelationships] = useState(null);

  const toggleChat = () => {
    setShowChat(prev => !prev);
    // Give D3 a moment then trigger a resize so force layout recalculates width
    setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
  };

  return (
    <SchemaProvider>
    <div id="cloud-container" className='border'>
      <Header/>
      
      {/* Where Used toolbar displayed as a normal row below header */}
      {activeTab === 'whereused' && (
        <div className='row' style={{ marginTop:'60px', paddingLeft:'15px', paddingRight:'15px' }}>
          <div className='col'>
            <div style={{
              display:'flex',
              alignItems:'center',
              gap:'12px',
              background:'#ffffff',
              border:'1px solid #e2e6ea',
              borderRadius:'8px',
              padding:'10px 14px',
              boxShadow:'0 2px 6px rgba(0,0,0,0.08)'
            }}>
              <button
                onClick={() => setActiveTab('graph')}
                style={{
                  backgroundColor:'#0a8276',
                  color:'#fff',
                  border:'1px solid #0a8276',
                  padding:'6px 12px',
                  borderRadius:'6px',
                  fontWeight:600,
                  cursor:'pointer'
                }}
              >← Back to Graph</button>
              <div style={{ color:'#0a8276', fontWeight:700, fontSize:'16px' }}>Where Used Analysis</div>
            </div>
          </div>
        </div>
      )}
      
      {/* Main interactive area below the header */}
  <div className={`cloud-main ${activeTab === 'whereused' ? 'whereused-wrapper' : ''}`}>        
        
        {activeTab === 'whereused' ? (
          // Where Used View (full screen)
          <div className='p-0' id="whereused-container" style={{ position:'relative', width:'100%' }}>
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
          </div>
        ) : (
          // Original layout with graph and chat
          <div className='row' style={{ flex: '1 1 auto', margin: 0 }}>
            {/* Left column: Tree visualization */}
            <div className={`graph-wrapper p-0 ${showChat ? 'col-md-8' : 'col-12'}`} id="graph-container">
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
                setActiveTab={setActiveTab}
              />
            </div>
            
            {/* Right column: Chatbot (conditional) */}
            {showChat && (
              <div className='graph-wrapper col-md-4 p-0' style={{ overflowY:'auto' }}>
                <Chatbot 
                  graphData={data} 
                  searchResults={searchResults} 
                  chatResults={chatResults}
                  setSearchResults={setSearchResults}
                  setChatResults={setChatResults}
                />
              </div>
            )}
          </div>
        )}
      </div>
      
      {/* Bottom navigation tabs (original location) - only show when NOT in where-used view */}
      {activeTab !== 'whereused' && (
  <div className='row' style={{ marginTop: '10px', paddingLeft: '15px', paddingRight: '15px' }}>
          <div className="col">
            <ul className="nav nav-tabs">
              <li className="nav-item">
                <button 
                  className={`nav-link ${activeTab === 'graph' ? 'active' : ''}`}
                  onClick={() => setActiveTab('graph')}
                  style={{ 
                    backgroundColor: activeTab === 'graph' ? '#0a8276' : 'transparent',
                    color: activeTab === 'graph' ? 'white' : '#0a8276',
                    border: '1px solid #0a8276'
                  }}
                >
                  Graph View
                </button>
              </li>
              <li className="nav-item">
                <button 
                  className={`nav-link ${activeTab === 'table' ? 'active' : ''}`}
                  onClick={() => setActiveTab('table')}
                  style={{ 
                    backgroundColor: activeTab === 'table' ? '#0a8276' : 'transparent',
                    color: activeTab === 'table' ? 'white' : '#0a8276',
                    border: '1px solid #0a8276'
                  }}
                >
                  Table View
                </button>
              </li>
              <li className="nav-item">
                <button 
                  className={`nav-link ${activeTab === 'reports' ? 'active' : ''}`}
                  onClick={() => setActiveTab('reports')}
                  style={{ 
                    backgroundColor: activeTab === 'reports' ? '#0a8276' : 'transparent',
                    color: activeTab === 'reports' ? 'white' : '#0a8276',
                    border: '1px solid #0a8276'
                  }}
                >
                  Reports & Data
                </button>
              </li>
            </ul>
          </div>
        </div>
      )}
      
      {/* Tab Content for bottom tabs */}
      {activeTab === 'table' && (
        <div className='row' style={{ marginTop: '10px' }}>
          <div className='table-wrapper col-12 p-0' id="table-container">
            <TableView
              data={data}
              searchResults={searchResults}
              chatResults={chatResults}
              visibleRelationships={visibleRelationships}
            />
          </div>
        </div>
      )}
      
      {activeTab === 'reports' && (
        <div className='row' style={{ marginTop: '10px' }}>
          <div className='reports-wrapper col-12 p-0' id="reports-container">
            <ReportsTab 
              searchResults={searchResults} 
              chatResults={chatResults}
              graphData={data}
            />
          </div>
        </div>
      )}
    </div>
    </SchemaProvider>
  );
}

export default App;