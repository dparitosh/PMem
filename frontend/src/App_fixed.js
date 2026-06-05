import 'bootstrap/dist/css/bootstrap.min.css';
import './App.css';
import 'bootstrap/dist/css/bootstrap.css';
import GraphHEB from "./Components/GraphHEB";
import Header from "./Components/Header";
import Chatbot from "./Components/Chatbot";
import TableView from './Components/TableView';
import ReportsTab from './Components/ReportsTab';
import WhereUsedView from './Components/WhereUsedView';
import { useState } from 'react';

function App() {
  const [data, setData] = useState();
  const [activeTab, setActiveTab] = useState('graph');
  const [searchResults, setSearchResults] = useState(null);
  const [chatResults, setChatResults] = useState(null);
  const [showChat, setShowChat] = useState(true);
  const [visibleRelationships, setVisibleRelationships] = useState(null);

  const toggleChat = () => {
    setShowChat(prev => !prev);
    // Give D3 a moment then trigger a resize so force layout recalculates width
    setTimeout(() => window.dispatchEvent(new Event('resize')), 60);
  };

  return (
    <div id="cloud-container" className='border'>
      <div className='row'>
        <div className='col vh-10'>
          <Header/>
        </div>
      </div>
      
      {/* Only show "Where Used" button in toolbar when in where-used view */}
      {activeTab === 'whereused' && (
        <div className='row' style={{ marginTop: '4px', paddingLeft: '15px', paddingRight: '15px' }}>
          <div className="col">
            <button 
              className="btn"
              onClick={() => setActiveTab('graph')}
              style={{ 
                backgroundColor: '#0a8276',
                color: 'white',
                border: '1px solid #0a8276',
                marginRight: '10px'
              }}
            >
              ← Back to Graph View
            </button>
            <span style={{ color: '#0a8276', fontWeight: 'bold', fontSize: '16px' }}>Where Used Analysis</span>
          </div>
        </div>
      )}
      
      {/* Main interactive area below the header */}
      <div className='row d-flex' style={{ marginTop: activeTab === 'whereused' ? '4px' : 'calc(8vh + 4px)', overflow: 'hidden' }}>
        
        {activeTab === 'whereused' ? (
          // Where Used View (full screen)
          <div className='col-12 p-0 vh-90' id="whereused-container">
            <WhereUsedView
              data={data}
            />
          </div>
        ) : (
          // Original layout with graph and chat
          <>
            {/* Left column: Tree visualization */}
            <div className={`${showChat ? 'col-md-8' : 'col-12'} p-0 vh-90`} id="graph-container">
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
              />
            </div>
            
            {/* Right column: Chatbot (conditional) */}
            {showChat && (
              <div className='col-md-4 p-0 vh-90'>
                <Chatbot 
                  graphData={data} 
                  searchResults={searchResults} 
                  chatResults={chatResults}
                  setSearchResults={setSearchResults}
                  setChatResults={setChatResults}
                />
              </div>
            )}
          </>
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
                  className={`nav-link`}
                  onClick={() => setActiveTab('whereused')}
                  style={{ 
                    backgroundColor: 'transparent',
                    color: '#0a8276',
                    border: '1px solid #0a8276'
                  }}
                >
                  Where Used
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
          <div className={`${showChat ? 'col-md-8' : 'col-12'} p-0 vh-90`} id="table-container">
            <TableView
              data={data}
              searchResults={searchResults}
              chatResults={chatResults}
              visibleRelationships={visibleRelationships}
            />
          </div>
          {showChat && (
            <div className='col-md-4 p-0 vh-90'>
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
      
      {activeTab === 'reports' && (
        <div className='row' style={{ marginTop: '10px' }}>
          <div className={`${showChat ? 'col-md-8' : 'col-12'} p-0 vh-90`} id="reports-container">
            <ReportsTab 
              searchResults={searchResults} 
              chatResults={chatResults}
              graphData={data}
            />
          </div>
          {showChat && (
            <div className='col-md-4 p-0 vh-90'>
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
  );
}

export default App;