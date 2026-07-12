import React, { useEffect, useMemo, useState } from 'react';
import { Clock3, Database, Plus, RefreshCw, Search, ShieldCheck } from 'lucide-react';
import { useOntologies } from '../contexts/OntologyContext';
import { API_METHODS } from '../services/apiClient';

const STATUS_LABELS = {
  approved: 'Approved',
  published: 'Published',
  uploaded: 'Review required',
  deprecated: 'Deprecated',
};

function statusLabel(value) {
  const key = String(value || '').toLowerCase();
  return STATUS_LABELS[key] || (value || 'Unclassified');
}

function statusTone(value) {
  const key = String(value || '').toLowerCase();
  if (['approved', 'published', 'available'].includes(key)) return '#147d72';
  if (['deprecated', 'rejected'].includes(key)) return '#b54708';
  return '#8a5a00';
}

export default function MetadataRegistryPage() {
  const { ontologies, loading, error, lastUpdated, fetchOntologies } = useOntologies();
  const [query, setQuery] = useState('');
  const [section, setSection] = useState('assets');
  const [selectedOntology, setSelectedOntology] = useState('');
  const [dictionary, setDictionary] = useState([]);
  const [dictionaryLoading, setDictionaryLoading] = useState(false);
  const [dictionaryError, setDictionaryError] = useState(null);
  const [dictionaryFilter, setDictionaryFilter] = useState('');
  const [prefixFilter, setPrefixFilter] = useState(null);
  const [registryAssets, setRegistryAssets] = useState([]);
  const [registryLoading, setRegistryLoading] = useState(false);
  const [registryMessage, setRegistryMessage] = useState(null);
  const [newAsset, setNewAsset] = useState({ name: '', definition: '', asset_type: 'DataElement', owner: '', steward: '', domain: '' });

  const loadRegistryAssets = async () => {
    setRegistryLoading(true);
    try {
      const response = await API_METHODS.metadataRegistry.list({ limit: 1000 });
      setRegistryAssets(response?.data?.assets || []);
    } catch (err) {
      setRegistryMessage({ kind: 'warning', text: err?.response?.data?.detail || err?.message || 'Governed registry is unavailable.' });
    } finally {
      setRegistryLoading(false);
    }
  };

  useEffect(() => { loadRegistryAssets(); }, []);

  const createAsset = async (event) => {
    event.preventDefault();
    if (!newAsset.name.trim()) return;
    try {
      const response = await API_METHODS.metadataRegistry.create(newAsset);
      setRegistryAssets((current) => [response.data, ...current]);
      setRegistryMessage({ kind: 'success', text: 'Metadata asset registered in the governed registry.' });
      setNewAsset({ name: '', definition: '', asset_type: 'DataElement', owner: '', steward: '', domain: '' });
    } catch (err) {
      setRegistryMessage({ kind: 'warning', text: err?.response?.data?.detail || err?.message || 'Metadata asset could not be registered.' });
    }
  };

  const entries = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return ontologies;
    return ontologies.filter((entry) => [
      entry.label,
      entry.prefix,
      entry.namespace,
      entry.type,
      entry.status,
    ].some((value) => String(value || '').toLowerCase().includes(needle)));
  }, [ontologies, query]);

  const reviewCount = ontologies.filter((entry) => {
    const status = String(entry.status || '').toLowerCase();
    return !['approved', 'published', 'available'].includes(status);
  }).length;
  const publishedCount = ontologies.length - reviewCount;
  const governedAssets = registryAssets.length > 0;

  const loadDictionary = async (ontologyId) => {
    setSelectedOntology(ontologyId);
    setDictionary([]);
    setDictionaryError(null);
    setPrefixFilter(null);
    if (!ontologyId) return;
    setDictionaryLoading(true);
    try {
      const response = await API_METHODS.ontology.getDataDictionary(ontologyId);
      const payload = response?.data?.data || {};
      const source = ontologies.find((entry) => (entry.ontology_id || entry.value || entry.prefix) === ontologyId);
      const prefix = response?.data?.prefix || source?.prefix || ontologyId;
      const nodes = [
        ...Object.entries(payload.entities || {}).map(([name, value]) => ({ term_id: `${prefix}:${name}`, label: name, ontology_prefix: prefix, source: 'class', definition: value?.definition || '' })),
        ...Object.entries(payload.properties || {}).map(([name, value]) => ({ term_id: `${prefix}:${name}`, label: name, ontology_prefix: prefix, source: 'data-property', definition: value?.definition || '' })),
        ...Object.entries(payload.relationships || {}).map(([name, value]) => ({ term_id: `${prefix}:${name}`, label: name, ontology_prefix: prefix, source: 'object-property', definition: value?.definition || '' })),
      ];
      setDictionary(nodes);
    } catch (err) {
      setDictionaryError(err?.response?.data?.detail || err?.message || 'Data Dictionary is unavailable for this source.');
    } finally {
      setDictionaryLoading(false);
    }
  };

  return (
    <div className="depo-page" style={{ display: 'grid', gap: 12 }}>
      <section className="depo-panel">
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Metadata Registry</div>
            <div className="depo-panel__meta">
              Governed catalog for definitions, ownership, lifecycle, versions, and physical implementations.
            </div>
          </div>
          <button type="button" className="depo-button depo-button--secondary" onClick={() => { fetchOntologies(); loadRegistryAssets(); }} disabled={loading || registryLoading}>
            <RefreshCw size={14} className={loading ? 'depo-spin' : ''} />
            Refresh catalog
          </button>
        </div>
        <div className="depo-panel__body" style={{ display: 'grid', gap: 12 }}>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }} role="tablist" aria-label="Metadata registry views">
            {[
              ['assets', 'Registry assets'],
              ['dictionary', 'Data Dictionary'],
            ].map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={section === id} onClick={() => setSection(id)}
                className="depo-button depo-button--secondary" style={section === id ? { background: '#123b67', color: '#fff' } : undefined}>
                {label}
              </button>
            ))}
          </div>
          {section === 'dictionary' && (
            <div style={{ display: 'grid', gap: 10 }}>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                <select className="depo-input" value={selectedOntology} onChange={(event) => loadDictionary(event.target.value)} aria-label="Select registry source for Data Dictionary">
                  <option value="">Select a registered source</option>
                  {ontologies.map((entry) => <option key={entry.ontology_id || entry.value || entry.prefix} value={entry.ontology_id || entry.value || entry.prefix}>{entry.label || entry.prefix}</option>)}
                </select>
                <input className="depo-input" value={dictionaryFilter} onChange={(event) => setDictionaryFilter(event.target.value)} placeholder="Filter terms" aria-label="Filter Data Dictionary terms" />
                {selectedOntology && <span className="depo-panel__meta">Dictionary terms are scoped to the selected source.</span>}
              </div>
              {dictionaryLoading && <div className="depo-empty">Loading dictionary terms...</div>}
              {dictionaryError && <div className="depo-alert depo-alert--warning">{dictionaryError}</div>}
              {!dictionaryLoading && selectedOntology && !dictionaryError && (
                <RegistryDictionaryTable nodes={dictionary} filter={dictionaryFilter} prefixFilter={prefixFilter} onPrefixFilterChange={setPrefixFilter} />
              )}
              {!selectedOntology && <div className="depo-empty">Select a registered source to inspect its terms, properties, and relationships.</div>}
            </div>
          )}
          {section === 'assets' && <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 8 }}>
            <Summary icon={<Database size={15} />} label="Governed assets" value={governedAssets ? registryAssets.length : ontologies.length} />
            <Summary icon={<ShieldCheck size={15} />} label="Published / available" value={publishedCount} />
            <Summary icon={<Clock3 size={15} />} label="Review required" value={reviewCount} />
          </div>
          <form onSubmit={createAsset} style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr 1fr 1fr auto', gap: 8, alignItems: 'end' }}>
            <label className="depo-field"><span>Name</span><input className="depo-input" value={newAsset.name} onChange={(event) => setNewAsset({ ...newAsset, name: event.target.value })} placeholder="e.g. Part number" /></label>
            <label className="depo-field"><span>Type</span><input className="depo-input" value={newAsset.asset_type} onChange={(event) => setNewAsset({ ...newAsset, asset_type: event.target.value })} /></label>
            <label className="depo-field"><span>Owner</span><input className="depo-input" value={newAsset.owner} onChange={(event) => setNewAsset({ ...newAsset, owner: event.target.value })} /></label>
            <label className="depo-field"><span>Domain</span><input className="depo-input" value={newAsset.domain} onChange={(event) => setNewAsset({ ...newAsset, domain: event.target.value })} /></label>
            <button type="submit" className="depo-button"><Plus size={14} /> Register</button>
          </form>
          {registryMessage && <div className={`depo-alert depo-alert--${registryMessage.kind}`}>{registryMessage.text}</div>}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, maxWidth: 560 }}>
            <Search size={15} color="#52606d" />
            <input
              className="depo-input"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search source, prefix, namespace, or status"
              aria-label="Search metadata registry"
            />
          </div>
          {error && <div className="depo-alert depo-alert--warning">Live registry unavailable: {error}</div>}
          {!loading && !entries.length && <div className="depo-empty">No registry entries match this search.</div>}
          {governedAssets ? <GovernedAssetsTable assets={registryAssets} onTransition={async (asset) => {
            try {
              const response = await API_METHODS.metadataRegistry.transition(asset.asset_id, { status: asset.lifecycle_status === 'approved' ? 'deprecated' : 'approved', actor: asset.owner || 'registry-user' });
              setRegistryAssets((current) => current.map((item) => item.asset_id === asset.asset_id ? response.data : item));
            } catch (err) { setRegistryMessage({ kind: 'warning', text: err?.response?.data?.detail || err?.message || 'Lifecycle transition failed.' }); }
          }} /> : entries.length > 0 && (
            <div style={{ overflowX: 'auto' }}>
              <table className="depo-table">
                <thead>
                  <tr>
                    <th>Source / ontology</th>
                    <th>Prefix</th>
                    <th>Namespace</th>
                    <th>Implementation</th>
                    <th>Lifecycle</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr key={entry.ontology_id || entry.value || entry.prefix}>
                      <td>
                        <strong>{entry.label || entry.ontology_id || entry.prefix}</strong>
                        <small style={{ display: 'block', color: '#697586', marginTop: 3 }}>{entry.type || 'Ontology source'}</small>
                      </td>
                      <td><code>{entry.prefix || '—'}</code></td>
                      <td style={{ maxWidth: 320, wordBreak: 'break-word' }}>{entry.namespace || '—'}</td>
                      <td>{entry.graph_available ? `${entry.node_count || 0} nodes · ${entry.relationship_count || 0} links` : 'Not projected'}</td>
                      <td><span style={{ color: statusTone(entry.status), fontWeight: 700 }}>{statusLabel(entry.status)}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="depo-panel__meta">
            This page is the governance boundary. Use Ontology Junction for OWL/RDF structure and Semantic Bridge for mappings. Registry editing, approvals, and version history will use dedicated registry APIs rather than adding more controls to Ontology Junction.
            {lastUpdated && ` Last refreshed ${lastUpdated.toLocaleTimeString()}.`}
          </div>
          </>}
        </div>
      </section>
    </div>
  );
}

function Summary({ icon, label, value }) {
  return (
    <div style={{ border: '1px solid #d9e2ec', borderRadius: 8, padding: '10px 12px', background: '#f8fafc' }}>
      <div style={{ display: 'flex', gap: 7, alignItems: 'center', color: '#52606d', fontSize: 11, fontWeight: 700 }}>{icon}{label}</div>
      <div style={{ marginTop: 4, color: '#102a43', fontSize: 20, fontWeight: 800 }}>{value}</div>
    </div>
  );
}

function RegistryDictionaryTable({ nodes, filter, prefixFilter, onPrefixFilterChange }) {
  const visible = nodes.filter((node) => {
    const needle = filter.trim().toLowerCase();
    return (!needle || [node.term_id, node.label, node.definition, node.source].some((value) => String(value || '').toLowerCase().includes(needle)))
      && (!prefixFilter || node.ontology_prefix === prefixFilter);
  });
  const prefixes = [...new Set(nodes.map((node) => node.ontology_prefix).filter(Boolean))].sort();

  return (
    <div style={{ border: '1px solid #d9e2ec', borderRadius: 8, overflow: 'auto', maxHeight: 520 }}>
      <div style={{ padding: '9px 12px', color: '#52606d', fontSize: 12, borderBottom: '1px solid #d9e2ec' }}>
        {visible.length} of {nodes.length} terms
        {prefixes.length > 0 && (
          <select value={prefixFilter || ''} onChange={(event) => onPrefixFilterChange(event.target.value || null)} style={{ marginLeft: 12, padding: '4px 8px' }} aria-label="Filter dictionary by prefix">
            <option value="">All prefixes</option>
            {prefixes.map((prefix) => <option key={prefix} value={prefix}>{prefix}</option>)}
          </select>
        )}
      </div>
      <table className="depo-table">
        <thead><tr><th>Term ID</th><th>Label</th><th>Type</th><th>Definition</th></tr></thead>
        <tbody>
          {visible.map((node) => (
            <tr key={`${node.term_id}:${node.source}`}>
              <td><code>{node.term_id}</code></td>
              <td><strong>{node.label || '—'}</strong></td>
              <td>{node.source || '—'}</td>
              <td>{node.definition || '—'}</td>
            </tr>
          ))}
          {!visible.length && <tr><td colSpan={4} style={{ textAlign: 'center', padding: 24 }}>No terms match the filter.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

function GovernedAssetsTable({ assets, onTransition }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="depo-table">
        <thead><tr><th>Name</th><th>Type</th><th>Owner / steward</th><th>Version</th><th>Lifecycle</th><th>Action</th></tr></thead>
        <tbody>{assets.map((asset) => (
          <tr key={asset.asset_id}>
            <td><strong>{asset.name}</strong><small style={{ display: 'block', color: '#697586' }}>{asset.asset_id}</small></td>
            <td>{asset.asset_type}</td><td>{asset.owner || '—'} / {asset.steward || '—'}</td><td>{asset.version}</td>
            <td><span style={{ color: statusTone(asset.lifecycle_status), fontWeight: 700 }}>{statusLabel(asset.lifecycle_status)}</span></td>
            <td><button type="button" className="depo-button depo-button--secondary" onClick={() => onTransition(asset)}>{asset.lifecycle_status === 'approved' ? 'Deprecate' : 'Approve'}</button></td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
