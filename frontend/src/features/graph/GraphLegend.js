import React from 'react';
import { getRelationshipDisplayName } from './graphRenderingPolicy';

export default function GraphLegend({ theme, ontologySliceSummary, getRelationshipVisual }) {
  return (ontologySliceSummary && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            gap: '8px',
            padding: '6px 10px',
            borderRadius: 6,
            border: `1px solid ${theme.border}`,
            background: theme.surface,
            color: theme.ink,
            maxWidth: '100%',
          }}
        >
          <span style={{ fontSize: 12, fontWeight: 700, color: theme.ink }}>{ontologySliceSummary.modeLabel || 'Current schema slice'}</span>
          <span style={{ fontSize: 12, color: theme.inkSoft }}>{ontologySliceSummary.nodeCount} nodes</span>
          <span style={{ fontSize: 12, color: theme.inkSoft }}>{ontologySliceSummary.relationshipCount} links</span>
          {ontologySliceSummary.totalCounts && (
            <span style={{ fontSize: 12, color: theme.primary, fontWeight: 700 }}>
              Total ontology: {ontologySliceSummary.totalCounts.nodes} nodes / {ontologySliceSummary.totalCounts.relationships} links
            </span>
          )}
          {ontologySliceSummary.isCapped && (
            <span style={{ fontSize: 11, color: 'var(--ui-warning)', background: 'var(--ui-warning-soft)', border: '1px solid var(--ui-warning)', borderRadius: 999, padding: '3px 8px', fontWeight: 700 }}>
              Showing capped slice
            </span>
          )}
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
                  background: theme.surfaceMuted,
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
              {getRelationshipDisplayName(entry.type)}: {entry.count}
              </span>
            );
          })}
          {ontologySliceSummary.visibleFamilies?.map((entry) => (
            <span
              key={entry.label}
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: theme.ink,
                background: theme.surfaceMuted,
                border: `1px solid ${theme.border}`,
                borderRadius: 999,
                padding: '3px 8px',
              }}
            >
              {entry.label}: {entry.count}
            </span>
          ))}
        </div>
      ));
}
