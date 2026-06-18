import React from 'react';
import { MessageSquare } from 'lucide-react';
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
        <div className="depo-rail__brand">
          <div className="depo-rail__brand-mark" aria-hidden="true">D</div>
          <div className="depo-rail__brand-text">
            <div className="depo-rail__brand-name">DEPO</div>
            <div className="depo-rail__brand-meta">Digital Thread</div>
          </div>
        </div>
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
              onClick={() => (item.id === 'home' ? onHome() : onPageChange(item.id))}
            >
              <Icon size={16} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      <header className="depo-topbar">
        <div className="depo-topbar__title">
          <h1>{pageLabel(activePage)}</h1>
        </div>
        <div className="depo-topbar__actions">
          <span className="depo-status">Online</span>
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
