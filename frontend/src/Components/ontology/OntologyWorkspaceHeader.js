import React from 'react';
import { Download, Network } from 'lucide-react';
import { UI_COLORS as C } from '../../styles/uiTokens';

export default function OntologyWorkspaceHeader({
  mappingOptionsError,
  selectedMapping,
  mappingOptions,
  applyOntologySelection,
  exportUrl,
  stats,
}) {
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: 'minmax(260px, 1fr) minmax(320px, 460px)', alignItems: 'center',
      gap: '12px', marginBottom: '8px',
      background: C.surface, border: `1px solid ${C.border}`, borderRadius: '6px', padding: '10px 12px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <div style={{
          width: 26,
          height: 26,
          borderRadius: 6,
          display: 'grid',
          placeItems: 'center',
          background: C.primaryLight,
          color: C.primary,
          flex: '0 0 auto',
        }}>
          <Network size={16} strokeWidth={2.4} />
        </div>
        <div>
          <div style={{ fontWeight: 800, fontSize: '13px', color: C.textPrimary }}>Ontology Junction</div>
          <div style={{ fontSize: '11px', color: C.textSec }}>Browse OWL terms, taxonomy, vocabulary, and semantic bridge mappings.</div>
        </div>
      </div>
      <div style={{ display: 'grid', gap: '6px', justifySelf: 'end', width: '100%', maxWidth: 460 }}>
        {mappingOptionsError && (
          <div style={{ color: C.red, fontSize: '12px', padding: '8px 12px', background: '#FFE5E5', border: `1px solid ${C.red}`, borderRadius: '6px' }}>
            {mappingOptionsError}
          </div>
        )}
        <div style={{ display: 'grid', gap: '4px' }}>
          <label style={{ fontSize: '10px', fontWeight: 700, color: C.textSec, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Active ontology</label>
          <select
            value={selectedMapping}
            onChange={(e) => applyOntologySelection(e.target.value)}
            disabled={mappingOptions.length === 0}
            style={{ minWidth: '320px', padding: '6px 10px', background: C.surface, border: `1px solid ${mappingOptionsError ? C.red : C.borderDark}`, color: C.textPrimary, borderRadius: '5px', fontWeight: 600, fontSize: '12px', cursor: mappingOptions.length === 0 ? 'not-allowed' : 'pointer', opacity: mappingOptions.length === 0 ? 0.6 : 1 }}
          >
            <option value="">{mappingOptions.length === 0 ? 'No ontologies loaded' : 'Select ontology'}</option>
            {Array.from(new Map(mappingOptions.map((o) => [o.prefix || o.value, o])).values()).map((o, idx) => (
              <option key={o.value || `mapping-${idx}`} value={o.value}>
                {o.label}{o.usageCount ? ` (used ${o.usageCount}x)` : ''}
              </option>
            ))}
          </select>
          {selectedMapping && (
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '4px' }}>
              {['ttl', 'rdf', 'owl', 'jsonld'].map((format) => (
                <a
                  key={format}
                  href={exportUrl(selectedMapping, format)}
                  target="_blank"
                  rel="noreferrer"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '4px 7px', border: `1px solid ${C.borderDark}`, borderRadius: '6px', color: C.primaryDark, background: C.surface, fontSize: '10px', fontWeight: 800, textDecoration: 'none', textTransform: 'uppercase' }}
                >
                  <Download size={11} /> {format}
                </a>
              ))}
            </div>
          )}
        </div>
        {stats && (
          <div style={{ fontSize: '11px', color: C.textSec, background: C.bg, border: `1px solid ${C.border}`, borderRadius: '20px', padding: '4px 10px' }}>
            {stats.total_terms} terms · {stats.total_vocabulary_mappings} mapping edges
          </div>
        )}
      </div>
    </div>
  );
}
