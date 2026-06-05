import React from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import '../CSS/SidebarNav.css';

/**
 * SidebarNav Component
 * Vertical sidebar navigation with collapsible toggle
 * Replaces horizontal tab bar for better space utilization
 */
const SidebarNav = ({ activeTab, onTabChange, isMobile = false, isCollapsed = false, onCollapsedChange = () => {} }) => {

  const tabs = [
    { id: 'graph', label: 'Graph', icon: '◈' },
    { id: 'table', label: 'Table', icon: '▦' },
    { id: 'reports', label: 'Reports', icon: '▲' },
    { id: 'ingestion', label: 'Data Import', icon: '↓' },
    { id: 'ontology', label: 'Ontology Mapper', icon: '◆' },
    { id: 'recommendations', label: 'Recommendations', icon: '★' },
  ];

  const handleTabClick = (tabId) => {
    onTabChange(tabId);
    // On mobile, collapse after selection for better UX
    if (isMobile) {
      onCollapsedChange(true);
    }
  };

  return (
    <div className={`sidebar-nav ${isCollapsed ? 'collapsed' : 'expanded'}`}>
      {/* Toggle Button */}
      <button
        className="sidebar-toggle"
        onClick={() => onCollapsedChange(!isCollapsed)}
        aria-label="Toggle sidebar"
        title={isCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {isCollapsed ? <ChevronRight size={20} /> : <ChevronLeft size={20} />}
      </button>

      {/* Navigation Links */}
      <nav className="sidebar-nav-list">
        {tabs.map(tab => (
          <button
            key={tab.id}
            className={`sidebar-nav-item ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => handleTabClick(tab.id)}
            title={tab.label}
          >
            <span className="sidebar-nav-icon">{tab.icon}</span>
            <span className="sidebar-nav-label">{tab.label}</span>
          </button>
        ))}
      </nav>

      {/* Sidebar Footer Info */}
      <div className="sidebar-footer">
        <div className="sidebar-info">
          <span className="info-label">Active Tab</span>
          <span className="info-value">
            {tabs.find(t => t.id === activeTab)?.label || 'Unknown'}
          </span>
        </div>
      </div>
    </div>
  );
};

export default SidebarNav;
