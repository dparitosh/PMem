import React from 'react';

const STATUS_LABELS = {
  draft: 'Draft',
  in_review: 'In review',
  approved: 'Approved',
  published: 'Published',
  uploaded: 'Review required',
  deprecated: 'Deprecated',
  retired: 'Retired',
};

const LIFECYCLE_ACTIONS = {
  draft: { status: 'in_review', label: 'Submit for review' },
  in_review: { status: 'approved', label: 'Approve' },
  approved: { status: 'deprecated', label: 'Deprecate' },
  deprecated: { status: 'retired', label: 'Retire' },
};

function statusLabel(value) {
  const key = String(value || '').toLowerCase();
  return STATUS_LABELS[key] || (value || 'Unclassified');
}

function statusTone(value) {
  const key = String(value || '').toLowerCase();
  if (['approved', 'published', 'available'].includes(key)) return '#147d72';
  if (['deprecated', 'rejected'].includes(key)) return '#b54708';
  if (key === 'retired') return '#52606d';
  return '#8a5a00';
}

function GovernedAssetsTable({ assets, onTransition, transitioningAssetIds }) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className="depo-table">
        <thead><tr><th>Name / definition</th><th>Type / domain</th><th>Owner / steward</th><th>Version</th><th>Lifecycle</th><th>Action</th></tr></thead>
        <tbody>{assets.map((asset) => {
          const action = LIFECYCLE_ACTIONS[String(asset.lifecycle_status || 'draft').toLowerCase()];
          const transitioning = transitioningAssetIds.has(asset.asset_id);
          return <tr key={asset.asset_id}>
            <td><strong>{asset.name}</strong><small style={{ display: 'block', color: '#697586' }}>{asset.definition || asset.asset_id}</small></td>
            <td>{asset.asset_type}<small style={{ display: 'block', color: '#697586' }}>{asset.domain || 'No domain'}</small></td><td>{asset.owner || '—'} / {asset.steward || '—'}</td><td>{asset.version}</td>
            <td><span style={{ color: statusTone(asset.lifecycle_status), fontWeight: 700 }}>{statusLabel(asset.lifecycle_status)}</span></td>
            <td>{action ? <button type="button" className="depo-button depo-button--secondary" disabled={transitioning} onClick={() => onTransition(asset, action)}>{transitioning ? 'Updating...' : action.label}</button> : <span className="depo-panel__meta">No action</span>}</td>
          </tr>;
        })}</tbody>
      </table>
    </div>
  );
}

export default function RegistryAssetsSection({
  newAsset,
  setNewAsset,
  createAsset,
  createLoading,
  registryMessage,
  query,
  setQuery,
  error,
  registryLoaded,
  loading,
  visibleRegistryAssets,
  registryAssets,
  entries,
  ontologiesTable,
  transitionHandler,
  transitioningAssetIds,
  lastUpdated,
}) {
  return (
    <>
      <form onSubmit={createAsset} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8, alignItems: 'end' }}>
        <label className="depo-field"><span>Name</span><input className="depo-input" value={newAsset.name} onChange={(event) => setNewAsset({ ...newAsset, name: event.target.value })} placeholder="e.g. Part number" /></label>
        <label className="depo-field"><span>Definition</span><input className="depo-input" value={newAsset.definition} onChange={(event) => setNewAsset({ ...newAsset, definition: event.target.value })} /></label>
        <label className="depo-field"><span>Type</span><input className="depo-input" value={newAsset.asset_type} onChange={(event) => setNewAsset({ ...newAsset, asset_type: event.target.value })} /></label>
        <label className="depo-field"><span>Owner</span><input className="depo-input" value={newAsset.owner} onChange={(event) => setNewAsset({ ...newAsset, owner: event.target.value })} /></label>
        <label className="depo-field"><span>Steward</span><input className="depo-input" value={newAsset.steward} onChange={(event) => setNewAsset({ ...newAsset, steward: event.target.value })} /></label>
        <label className="depo-field"><span>Domain</span><input className="depo-input" value={newAsset.domain} onChange={(event) => setNewAsset({ ...newAsset, domain: event.target.value })} /></label>
        <button type="submit" className="depo-button" disabled={createLoading || !newAsset.name.trim()}>{createLoading ? 'Registering...' : 'Register'}</button>
      </form>
      {registryMessage && <div className={`depo-alert depo-alert--${registryMessage.kind}`}>{registryMessage.text}</div>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, maxWidth: 560 }}>
        <input
          className="depo-input"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search source, prefix, namespace, or status"
          aria-label="Search metadata registry"
        />
      </div>
      {error && !registryLoaded && <div className="depo-alert depo-alert--warning">Live registry unavailable: {error}</div>}
      {!loading && registryLoaded && !visibleRegistryAssets.length && <div className="depo-empty">{registryAssets.length ? 'No governed assets match this search.' : 'No governed metadata assets are registered yet.'}</div>}
      {!loading && !registryLoaded && !entries.length && <div className="depo-empty">No registry entries match this search.</div>}
      {registryLoaded ? <GovernedAssetsTable assets={visibleRegistryAssets} transitioningAssetIds={transitioningAssetIds} onTransition={transitionHandler} /> : ontologiesTable}
      {registryLoaded && ontologiesTable && (
        <section style={{ marginTop: 12 }} aria-label="Registered ontology sources">
          <div className="depo-panel__title" style={{ fontSize: 14, marginBottom: 6 }}>Registered ontology sources</div>
          <div className="depo-panel__meta" style={{ marginBottom: 8 }}>
            These sources are available for browsing and dictionary inspection. Create a governed asset above when ownership, stewardship, and lifecycle approval are required.
          </div>
          {ontologiesTable}
        </section>
      )}
      <div className="depo-panel__meta">
        This page is the governance boundary. Use Ontology Junction for OWL/RDF structure and Semantic Bridge for mappings. Registry editing, approvals, and version history will use dedicated registry APIs rather than adding more controls to Ontology Junction.
        {lastUpdated && ` Last refreshed ${lastUpdated.toLocaleTimeString()}.`}
      </div>
    </>
  );
}
