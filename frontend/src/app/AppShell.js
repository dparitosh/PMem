import React from 'react';
import { Home, MessageSquare } from 'lucide-react';
import { navigationItems, pageLabel } from './navigation';
import './AppShell.css';

export default function AppShell({
  activePage,
  onPageChange,
  onHome,
  showChat,
  onToggleChat,
  rightDrawer,
  children,
}) {
  return (
    <div className="depo-shell">
      <nav className="depo-rail" aria-label="Application navigation">
        <div className="depo-rail__brand">DEPO</div>
        <button type="button" className="depo-rail__button" title="Home" onClick={onHome}>
          <Home size={15} />
        </button>
        {navigationItems.map((item) => {
          const Icon = item.icon;
          const active = item.id === activePage;
          return (
            <button
              key={item.id}
              type="button"
              className={`depo-rail__button ${active ? 'is-active' : ''}`}
              title={item.label}
              aria-label={item.label}
              onClick={() => onPageChange(item.id)}
            >
              <Icon size={15} />
            </button>
          );
        })}
      </nav>

      <header className="depo-topbar">
        <div className="depo-topbar__title">
          <h1>{pageLabel(activePage)}</h1>
          <div className="depo-topbar__context">Workspace: Lab Sandbox | Dataset: Current graph | Ontology: Active context</div>
        </div>
        <input className="depo-topbar__search" placeholder="Search graph, ontology, workflow, service" />
        <div className="depo-topbar__actions">
          <span className="depo-status">API online</span>
          <button type="button" className="depo-icon-button" title="Toggle chat" onClick={onToggleChat}>
            <MessageSquare size={16} fill={showChat ? '#eef5fb' : 'none'} />
          </button>
        </div>
      </header>

      <main className="depo-main">
        <div className="depo-content">{children}</div>
        {showChat && rightDrawer && <aside className="depo-drawer">{rightDrawer}</aside>}
      </main>
    </div>
  );
}
