import React from 'react';
import {
  Database,
  Globe,
  Loader2,
  MessageSquare,
  Network,
  RefreshCcw,
  Search,
  Settings,
  Workflow,
  X,
} from 'lucide-react';


const SEARCH_MODES = [
  { id: 'best', label: 'Best Match', title: 'Best match only' },
  { id: 'broader', label: 'Many Matches', title: 'Return multiple matching nodes' },
];

const VIEW_MODES = [
  { id: 'full', label: 'Full Graph', Icon: Globe },
  { id: 'ontology', label: 'Ontology Schema', Icon: Workflow },
  { id: 'architecture', label: 'Architecture Process', Icon: Network },
  { id: 'individual', label: 'Contextual Instances', Icon: Network },
];

function GraphExplorerToolbar({
  theme,
  graphViewMode,
  selectedOntology,
  searchInput,
  onSearchInputChange,
  onSearchSubmit,
  searchLoading,
  searchResultMode,
  onSearchResultModeChange,
  onOpenFullGraph,
  onOpenOntologyGraph,
  onOpenArchitectureGraph,
  onOpenContextualGraph,
  ontologyLoading,
  ontologyError,
  ontologyOptions,
  onSelectedOntologyChange,
  selectedStepPart,
  stepPartsLoading,
  stepPartsError,
  stepParts,
  onSelectedStepPartChange,
  isLayoutSwitching,
  ontologyGraphMessage,
  ontologySliceSummary,
  getRelationshipVisual,
  graphSearchActive,
  onReset,
  showChat,
  onToggleChat,
}) {

  const viewModeState = {
    full: graphViewMode === 'ontology' && selectedOntology === 'ALL',
    ontology: graphViewMode === 'ontology' && selectedOntology !== 'ALL' && selectedOntology !== 'archimate',
    architecture: graphViewMode === 'ontology' && selectedOntology === 'archimate',
    individual: graphViewMode === 'individual',
  };
  const trimmedSearch = String(searchInput || '').trim();
  const showClearSearch = Boolean(trimmedSearch || graphSearchActive);

  return (
    <div
      className="graph-toolbar"
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '6px',
        alignItems: 'center',
        padding: '6px 10px',
        background: theme.surface,
        border: `1px solid ${theme.border}`,
        borderRadius: '8px',
        boxShadow: '0 6px 18px rgba(15, 23, 42, 0.08)',
        zIndex: 1500,
        position: 'relative',
        flex: '0 0 auto',
        pointerEvents: 'auto',
      }}
    >
      <div style={{ display: 'inline-flex', alignItems: 'center', gap: 4, border: `1px solid ${theme.borderStrong}`, borderRadius: 6, padding: 2, background: theme.surfaceMuted, maxWidth: '100%', flexWrap: 'wrap' }}>
        {VIEW_MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            title={mode.label}
            aria-label={mode.label}
            onClick={() => {
              if (mode.id === 'full') return onOpenFullGraph?.();
              if (mode.id === 'architecture') return onOpenArchitectureGraph?.();
              if (mode.id === 'individual') return onOpenContextualGraph?.();
              return onOpenOntologyGraph?.();
            }}
            style={{
              width: 38,
              height: 34,
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: 'none',
              borderRadius: 6,
              background: viewModeState[mode.id] ? theme.primary : 'transparent',
              color: viewModeState[mode.id] ? '#fff' : theme.inkSoft,
              cursor: 'pointer',
              padding: 0,
              fontWeight: 800,
              lineHeight: 0,
              overflow: 'hidden',
            }}
          >
            <mode.Icon
              size={16}
              strokeWidth={2.8}
              color={viewModeState[mode.id] ? '#fff' : theme.inkSoft}
              className="graph-toolbar-icon"
              style={{ display: 'block', flex: '0 0 auto' }}
            />
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', position: 'relative', flexWrap: 'wrap' }}>
        <Search size={17} color={theme.inkSoft} strokeWidth={2.4} aria-hidden="true" />
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const currentValue = event.currentTarget.querySelector('input')?.value ?? searchInput;
            onSearchSubmit?.(currentValue);
          }}
          style={{ display: 'flex', alignItems: 'center', gap: '6px', position: 'relative' }}
        >
          <input
            type="text"
            placeholder={graphViewMode === 'individual' ? 'Search instances, type, label, properties...' : 'Search nodes...'}
            value={searchInput}
            style={{
              padding: '6px 10px',
              borderRadius: '6px',
              border: `1px solid ${theme.borderStrong}`,
              minWidth: '190px',
              fontSize: '13px',
              fontWeight: 500,
              lineHeight: 1.2,
              background: theme.surface,
              color: theme.ink,
            }}
            onChange={(event) => onSearchInputChange?.(event.target.value)}
            onFocus={(event) => {
              event.target.style.borderColor = theme.primary;
              event.target.style.boxShadow = '0 0 0 2px rgba(31,61,99,0.12)';
            }}
            onBlur={(event) => {
              event.target.style.borderColor = theme.borderStrong;
              event.target.style.boxShadow = 'none';
            }}
          />
          <button
            type="button"
            onClick={(event) => {
              const currentValue = event.currentTarget.form?.querySelector('input')?.value ?? searchInput;
              onSearchSubmit?.(currentValue);
            }}
            disabled={searchLoading}
            style={{
              height: 30,
              padding: '0 12px',
              border: 'none',
              borderRadius: 6,
              background: theme.primary,
              color: '#fff',
              fontSize: 12,
              fontWeight: 700,
              cursor: searchLoading ? 'not-allowed' : 'pointer',
              flex: '0 0 auto',
              opacity: searchLoading ? 0.72 : 1,
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            {searchLoading && <Loader2 size={13} className="spinner" />}
            Search
          </button>
          {showClearSearch && (
            <button
              type="button"
              title="Clear search"
              aria-label="Clear search"
              onClick={() => {
                onSearchInputChange?.('');
                onSearchSubmit?.('');
              }}
              style={{
                width: 30,
                height: 30,
                border: `1px solid ${theme.borderStrong}`,
                borderRadius: 6,
                background: theme.surface,
                color: theme.inkSoft,
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                padding: 0,
              }}
            >
              <X size={14} strokeWidth={2.4} />
            </button>
          )}
        </form>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 2, border: `1px solid ${theme.borderStrong}`, borderRadius: 6, padding: 2, background: theme.surfaceMuted }}>
          {SEARCH_MODES.map((mode) => (
            <button
              key={mode.id}
              type="button"
              title={mode.title}
              aria-label={mode.title}
              onClick={() => onSearchResultModeChange?.(mode.id)}
              style={{
                minWidth: mode.id === 'best' ? 80 : 98,
                height: 28,
                padding: '0 10px',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: 'none',
                borderRadius: 4,
                background: searchResultMode === mode.id ? theme.primary : 'transparent',
                color: searchResultMode === mode.id ? '#fff' : theme.inkSoft,
                cursor: 'pointer',
                fontSize: 10.5,
                fontWeight: 800,
                lineHeight: 1,
              }}
            >
              {mode.label}
            </button>
          ))}
        </div>
      </div>

      {graphViewMode === 'ontology' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Database size={15} color={theme.inkSoft} strokeWidth={2.4} aria-hidden="true" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <select
              value={selectedOntology}
              onChange={(event) => onSelectedOntologyChange?.(event.target.value)}
              disabled={ontologyLoading || !!ontologyError}
              style={{
                padding: '6px 10px',
                borderRadius: '6px',
                border: ontologyError ? '1px solid #D32F2F' : `1px solid ${theme.borderStrong}`,
                backgroundColor: theme.surface,
                color: theme.ink,
                cursor: ontologyLoading || ontologyError ? 'not-allowed' : 'pointer',
                fontSize: '13px',
                fontWeight: 600,
                minWidth: '200px',
                transition: 'all .2s ease',
                opacity: ontologyLoading || ontologyError ? 0.6 : 1,
              }}
              title={ontologyError ? ontologyError : 'Select an ontology'}
            >
              <option value="ALL" style={{ color: '#333', fontWeight: 600 }}>Overview Graph (all loaded data)</option>
              <option value="archimate" style={{ color: '#333', fontWeight: 600 }}>[archimate] ArchiMate process model</option>
              {ontologyOptions.filter((option) => option.value !== 'ALL' && option.value !== 'archimate').map((option, index) => (
                <option key={option.value || `ontology-opt-${index}`} value={option.value} style={{ color: '#333' }}>
                  {option.prefix ? `[${option.prefix}] ` : ''}{option.label}{option.type ? ` · ${option.type}` : ''}{option.graph_available === false ? ' · registered only' : Number(option.relationship_count || 0) === 0 ? ' · classes only' : ''}
                </option>
              ))}
            </select>
            {ontologyError && <span style={{ fontSize: '11px', color: '#D32F2F' }}>Warning: {ontologyError}</span>}
          </div>
        </div>
      )}

      {graphViewMode === 'ontology' && selectedOntology === 'step' && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Settings size={15} color={theme.inkSoft} strokeWidth={2.4} aria-hidden="true" />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <select
              value={selectedStepPart}
              onChange={(event) => onSelectedStepPartChange?.(event.target.value)}
              disabled={stepPartsLoading || ontologyLoading || !!stepPartsError}
              style={{
                padding: '6px 10px',
                borderRadius: '6px',
                border: stepPartsError ? '1px solid #D32F2F' : '1px solid #cfd6dc',
                backgroundColor: '#fff',
                color: '#333',
                cursor: stepPartsLoading || ontologyLoading || stepPartsError ? 'not-allowed' : 'pointer',
                fontSize: '13px',
                fontWeight: 500,
                minWidth: '200px',
                maxWidth: '320px',
                transition: 'all .2s ease',
                opacity: stepPartsLoading || ontologyLoading || stepPartsError ? 0.6 : 1,
              }}
              title={stepPartsError ? stepPartsError : 'Filter STEP data by part'}
            >
              <option key="ALL" value="ALL" style={{ color: '#333' }}>
                All Parts{stepParts.length > 0 ? ` (${stepParts.length})` : ''}
              </option>
              {stepParts.map((part) => (
                <option key={part} value={part} style={{ color: '#333' }}>
                  {part.replace(/_/g, ' ')}
                </option>
              ))}
            </select>
            {stepPartsError && <span style={{ fontSize: '11px', color: '#D32F2F' }}>Warning: {stepPartsError}</span>}
          </div>
        </div>
      )}

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          fontSize: 13,
          color: '#004B87',
          minWidth: 148,
          visibility: (searchLoading || isLayoutSwitching || ontologyLoading) ? 'visible' : 'hidden',
        }}
      >
        <Loader2 size={14} className="spinner" />
        {searchLoading ? 'Searching...' : ontologyLoading ? 'Loading ontology...' : 'Switching layout...'}
      </div>

      {ontologyGraphMessage && (
        <div style={{ fontSize: 12, color: '#8a5a00', background: '#fff8e1', border: '1px solid #ffe082', borderRadius: 5, padding: '5px 8px' }}>
          {ontologyGraphMessage}
        </div>
      )}

      {ontologySliceSummary && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 10px',
            borderRadius: 6,
            border: `1px solid ${theme.border}`,
            background: '#ffffff',
            color: theme.ink,
            maxWidth: '100%',
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 700, color: theme.ink }}>Current schema slice</span>
          <span style={{ fontSize: 12, color: theme.inkSoft }}>{ontologySliceSummary.nodeCount} nodes</span>
          <span style={{ fontSize: 12, color: theme.inkSoft }}>{ontologySliceSummary.relationshipCount} links</span>
          {ontologySliceSummary.visibleSchemaLabels.map((entry) => (
            <span
              key={entry.label}
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: theme.ink,
                background: theme.surfaceAccent,
                border: `1px solid ${theme.border}`,
                borderRadius: 999,
                padding: '3px 8px',
              }}
            >
              {entry.label}: {entry.count}
            </span>
          ))}
          {ontologySliceSummary.visibleRelationships.map((entry) => {
            const visual = getRelationshipVisual(entry.type);
            return (
              <span
                key={entry.type}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: 11,
                  fontWeight: 600,
                  color: theme.ink,
                  background: '#f8fafc',
                  border: `1px solid ${theme.border}`,
                  borderRadius: 999,
                  padding: '3px 8px',
                }}
              >
                <span
                  aria-hidden="true"
                  style={{
                    width: 16,
                    height: 0,
                    borderTop: `${Math.max(2, Math.round(visual.width))}px ${visual.dasharray ? 'dashed' : 'solid'} ${visual.color}`,
                    display: 'inline-block',
                  }}
                />
                {entry.type}: {entry.count}
              </span>
            );
          })}
        </div>
      )}

      <button
        onClick={onReset}
        title="Reset graph"
        style={{ padding: '5px 10px', border: 'none', borderRadius: '6px', backgroundColor: theme.primary, color: '#fff', fontSize: '12px', fontWeight: 700, cursor: 'pointer', transition: 'all .2s ease', opacity: (graphSearchActive || selectedOntology !== 'ALL' || graphViewMode !== 'ontology') ? 1 : 0.78, display: 'inline-flex', alignItems: 'center', gap: 6 }}
      >
        <RefreshCcw size={13} strokeWidth={2.4} />
        Reset
      </button>
      <button
        onClick={onToggleChat}
        style={{ padding: '5px 10px', border: 'none', borderRadius: '6px', backgroundColor: theme.primary, color: '#fff', fontSize: '12px', fontWeight: 700, cursor: 'pointer', transition: 'all .2s ease', display: 'inline-flex', alignItems: 'center', gap: 6 }}
        title={showChat ? 'Hide chat assistant' : 'Show chat assistant'}
      >
        <MessageSquare size={13} strokeWidth={2.4} />
        {showChat ? 'Hide Chat' : 'Show Chat'}
      </button>
    </div>
  );
}

export default GraphExplorerToolbar;
