import { dictionaryPayload } from '../services/ontologyPayload';
import './MetadataRegistryPage.css';
import WorkspaceTabs from '../Components/WorkspaceTabs';
import { apiErrorMessage } from '../utils/apiErrorMessage';
import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Clock3, Database, RefreshCw, ShieldCheck } from 'lucide-react';
import { useOntologies } from '../contexts/OntologyContext';
import { API_METHODS } from '../services/apiClient';
import RegistrySummaryCards from '../Components/registry/RegistrySummaryCards';
import RegistryAssetsSection from '../Components/registry/RegistryAssetsSection';
import { metadataAssetsPayload, dictionaryAssetDraft } from '../services/metadataRegistryPayload';

const STATUS_LABELS = {
  draft: 'Draft',
  in_review: 'In review',
  approved: 'Approved',
  published: 'Published',
  uploaded: 'Review required',
  deprecated: 'Deprecated',
  retired: 'Retired',
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

function RegistryDictionaryTable({ nodes, filter, prefixFilter, onPrefixFilterChange, onRegister, disabled }) {
  const visible = nodes.filter((node) => {
    const needle = filter.trim().toLowerCase();
    return (!needle || [node.term_id, node.label, node.definition, node.source].some((value) => String(value || '').toLowerCase().includes(needle)))
      && (!prefixFilter || node.ontology_prefix === prefixFilter);
  });
  const prefixes = [...new Set(nodes.map((node) => node.ontology_prefix).filter(Boolean))].sort();

  const [page, setPage] = useState(0);
  const pageSize = 25;
  const lastPage = Math.max(0, Math.ceil(visible.length / pageSize) - 1);
  const currentPage = Math.min(page, lastPage);
  useEffect(() => setPage(0), [filter, prefixFilter, nodes]);
  return <section className="registry-dictionary" aria-label="Dictionary terms">
    <div className="registry-dictionary__toolbar"><strong>{visible.length} of {nodes.length} terms</strong>
      {prefixes.length > 0 && <label>Prefix <select value={prefixFilter || ''} onChange={event => onPrefixFilterChange(event.target.value || null)} aria-label="Filter dictionary by prefix"><option value="">All prefixes</option>{prefixes.map(prefix => <option key={prefix}>{prefix}</option>)}</select></label>}
    </div>
    <div className="registry-dictionary__scroll"><table className="registry-dictionary__table">
      <colgroup><col style={{width:'28%'}}/><col style={{width:'14%'}}/><col style={{width:'43%'}}/><col style={{width:'15%'}}/></colgroup>
      <thead><tr><th scope="col">Term</th><th scope="col">Type</th><th scope="col">Definition</th><th scope="col">Action</th></tr></thead>
      <tbody>{visible.slice(currentPage*pageSize,(currentPage+1)*pageSize).map(node => <tr key={`${node.term_id}:${node.source}`}>
        <td><strong>{node.label || 'Unnamed term'}</strong><details><summary>Term identity</summary><code>{node.term_id}</code></details></td>
        <td><span className="registry-dictionary__type">{node.source || 'Unspecified'}</span></td>
        <td><p className="registry-dictionary__definition">{node.definition || 'No definition provided.'}</p>{node.definition?.length > 220 && <details><summary>Read full definition</summary><p>{node.definition}</p></details>}</td>
        <td><button className="depo-button depo-button--secondary" type="button" aria-label="Prepare draft registration" disabled={disabled} onClick={()=>onRegister(node)}>Prepare draft</button></td>
      </tr>)}{!visible.length && <tr><td colSpan={4}>No terms match the filter.</td></tr>}</tbody>
    </table></div>
    <nav className="registry-dictionary__pagination" aria-label="Dictionary pages"><span>Page {currentPage+1} of {lastPage+1} · 25 terms per page</span><button disabled={currentPage===0} onClick={()=>setPage(currentPage-1)}>Previous</button><button disabled={currentPage>=lastPage} onClick={()=>setPage(currentPage+1)}>Next</button></nav>
  </section>;

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
  const [registryOffset, setRegistryOffset] = useState(0);
  const [registryHasMore, setRegistryHasMore] = useState(false);
  const [registryLoaded, setRegistryLoaded] = useState(false);
  const [registryStale, setRegistryStale] = useState(false);
  const [registryLoading, setRegistryLoading] = useState(false);
  const [createLoading, setCreateLoading] = useState(false);
  const [transitioningAssetIds, setTransitioningAssetIds] = useState(new Set());
  const [registryMessage, setRegistryMessage] = useState(null);
  const [governanceAction, setGovernanceAction] = useState(null);
  const [governanceEvidence, setGovernanceEvidence] = useState('');
  const [newAsset, setNewAsset] = useState({ name: '', definition: '', asset_type: 'DataElement', owner: '', steward: '', domain: '' });
  const registryControllerRef = useRef(null);
  const dictionaryControllerRef = useRef(null);
  const refreshReadRef = useRef(null);
  const mutationControllersRef = useRef(new Set());

  const loadRegistryAssets = async (offset = 0) => {
    registryControllerRef.current?.abort();
    const controller = new AbortController();
    registryControllerRef.current = controller;
    setRegistryLoading(true);
    try {
      const response = await API_METHODS.metadataRegistry.list({ limit: 1000, offset }, { signal: controller.signal });
      if (controller.signal.aborted || registryControllerRef.current !== controller) return;
      setRegistryAssets(metadataAssetsPayload(response?.data));
      setRegistryOffset(offset);
      setRegistryHasMore(response?.data?.has_more === true);
      setRegistryLoaded(true);
      setRegistryStale(false);
      setRegistryMessage(response?.data?.has_more === undefined && response?.data?.assets?.length === 1000
        ? { kind: 'warning', text: 'This service returned the maximum 1,000 assets without pagination metadata. Update the ontology service to browse remaining assets.' } : null);
    } catch (err) {
      if (controller.signal.aborted) return;
      setRegistryLoaded(false);
      setRegistryStale(true);
      setRegistryMessage({ kind: 'warning', text: apiErrorMessage(err, 'Governed registry is unavailable.') });
    } finally {
      if (!controller.signal.aborted) setRegistryLoading(false);
      if (registryControllerRef.current === controller) registryControllerRef.current = null;
    }
  };

  useEffect(() => {
    const mutationControllers = mutationControllersRef.current;
    const resetSession = () => {
      registryControllerRef.current?.abort();
      dictionaryControllerRef.current?.abort();
      mutationControllers.forEach(controller => controller.abort());
      mutationControllers.clear();
      setRegistryAssets([]);
      setRegistryLoaded(false);
      setRegistryStale(false);
      setRegistryOffset(0);
      setRegistryHasMore(false);
      setRegistryMessage(null);
      setGovernanceAction(null); setGovernanceEvidence('');
      setSelectedOntology('');
      setDictionary([]);
      setDictionaryLoading(false);
      setDictionaryError(null);
      setPrefixFilter(null);
      setCreateLoading(false);
      setTransitioningAssetIds(new Set());
      setNewAsset({ name: '', definition: '', asset_type: 'DataElement', owner: '', steward: '', domain: '' });
      loadRegistryAssets();
    };
    const sessionEvents = ['depo:credentials-changed','depo:credentials-cleared','depo:session-replaced','depo:session-expired'];
    sessionEvents.forEach(name => window.addEventListener(name, resetSession));
    const refreshReads = () => refreshReadRef.current?.();
    window.addEventListener('depo:access-verified', refreshReads);
    loadRegistryAssets();
    return () => {
      sessionEvents.forEach(name => window.removeEventListener(name, resetSession));
      window.removeEventListener('depo:access-verified', refreshReads);
      registryControllerRef.current?.abort();
      dictionaryControllerRef.current?.abort();
      mutationControllers.forEach((controller) => controller.abort());
      mutationControllers.clear();
    };
  }, []);

  const createAsset = async (event) => {
    event.preventDefault();
    if (!newAsset.name.trim() || createLoading) return;
    const controller = new AbortController();
    registryControllerRef.current?.abort();
    registryControllerRef.current = null;
    setRegistryLoading(false);
    mutationControllersRef.current.add(controller);
    setCreateLoading(true);
    try {
      const response = await API_METHODS.metadataRegistry.create(newAsset, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setRegistryAssets((current) => [response.data, ...current]);
      setRegistryLoaded(true);
      setRegistryMessage({ kind: 'success', text: 'Metadata asset registered in the governed registry.' });
      setNewAsset({ name: '', definition: '', asset_type: 'DataElement', owner: '', steward: '', domain: '' });
    } catch (err) {
      if (controller.signal.aborted) return;
      setRegistryMessage({ kind: 'warning', text: apiErrorMessage(err, 'Metadata asset could not be registered.') });
    } finally {
      mutationControllersRef.current.delete(controller);
      if (!controller.signal.aborted) setCreateLoading(false);
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

  const summaryStatuses = registryLoaded
    ? registryAssets.map((asset) => asset.lifecycle_status)
    : ontologies.map((entry) => entry.status);
  const publishedCount = summaryStatuses.filter((status) => ['approved', 'published', 'available'].includes(String(status || '').toLowerCase())).length;
  const reviewCount = summaryStatuses.filter((status) => ['draft', 'in_review', 'uploaded', ''].includes(String(status || '').toLowerCase())).length;
  const visibleRegistryAssets = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return registryAssets;
    return registryAssets.filter((asset) => [
      asset.name,
      asset.asset_id,
      asset.asset_type,
      asset.definition,
      asset.owner,
      asset.steward,
      asset.domain,
      asset.lifecycle_status,
    ].some((value) => String(value || '').toLowerCase().includes(needle)));
  }, [query, registryAssets]);

  const loadDictionary = async (ontologyId) => {
    dictionaryControllerRef.current?.abort();
    const controller = new AbortController();
    dictionaryControllerRef.current = controller;
    setSelectedOntology(ontologyId);
    setDictionary([]);
    setDictionaryError(null);
    setPrefixFilter(null);
    if (!ontologyId) {
      setDictionaryLoading(false);
      return;
    }
    setDictionaryLoading(true);
    try {
      const response = await API_METHODS.ontology.getDataDictionary(ontologyId, { signal: controller.signal });
      if (controller.signal.aborted || dictionaryControllerRef.current !== controller) return;
      const payload = dictionaryPayload(response?.data);
      const source = ontologies.find((entry) => (entry.ontology_id || entry.value || entry.prefix) === ontologyId);
      const prefix = response?.data?.prefix || source?.prefix || ontologyId;
      const nodes = [
        ...Object.entries(payload.entities || {}).map(([name, value]) => ({ term_id: value?.iri || `${prefix}:${name}`, label: name, ontology_prefix: prefix, source: 'class', definition: value?.definition || '' })),
        ...Object.entries(payload.properties || {}).map(([name, value]) => ({ term_id: value?.iri || `${prefix}:${name}`, label: name, ontology_prefix: prefix, source: 'data-property', definition: value?.definition || '' })),
        ...Object.entries(payload.relationships || {}).map(([name, value]) => ({ term_id: value?.iri || `${prefix}:${name}`, label: name, ontology_prefix: prefix, source: 'object-property', definition: value?.definition || '' })),
      ];
      setDictionary(nodes);
    } catch (err) {
      if (controller.signal.aborted) return;
      setDictionaryError(apiErrorMessage(err, 'Data Dictionary is unavailable for this source.'));
    } finally {
      if (!controller.signal.aborted) setDictionaryLoading(false);
      if (dictionaryControllerRef.current === controller) dictionaryControllerRef.current = null;
    }
  };

  refreshReadRef.current = () => {
    loadRegistryAssets(registryOffset);
    if (selectedOntology) loadDictionary(selectedOntology);
  };

  const transitionHandler = async (asset, action, evidence = {}) => {
    if (!action || transitioningAssetIds.has(asset.asset_id)) return;
    if ((action.status === 'approved' && !evidence.approval_evidence) ||
        (['deprecated','retired'].includes(action.status) && !evidence.deprecation_reason)) {
      setGovernanceAction({asset,action}); setGovernanceEvidence(''); return;
    }
    const controller = new AbortController();
    registryControllerRef.current?.abort();
    registryControllerRef.current = null;
    setRegistryLoading(false);
    mutationControllersRef.current.add(controller);
    setTransitioningAssetIds((current) => new Set(current).add(asset.asset_id));
    try {
      const response = await API_METHODS.metadataRegistry.transition(asset.asset_id, { status: action.status, ...evidence }, { signal: controller.signal });
      if (controller.signal.aborted) return;
      setRegistryAssets((current) => current.map((item) => item.asset_id === asset.asset_id ? response.data : item));
      setGovernanceAction(null);
      setRegistryMessage({ kind: 'success', text: `Lifecycle changed to ${statusLabel(action.status)}.` });
    } catch (err) {
      if (!controller.signal.aborted) {
        setRegistryMessage({ kind: 'warning', text: apiErrorMessage(err, 'Lifecycle transition failed.') });
      }
    } finally {
      mutationControllersRef.current.delete(controller);
      if (!controller.signal.aborted) {
        setTransitioningAssetIds((current) => {
          const next = new Set(current);
          next.delete(asset.asset_id);
          return next;
        });
      }
    }
  };

  return (
    <div className="depo-page" style={{ display: 'grid', gap: 12 }}>
      {governanceAction && <section className="depo-panel" aria-label="Metadata governance evidence">
        <form onSubmit={event => {
          event.preventDefault();
          const key = governanceAction.action.status === 'approved' ? 'approval_evidence' : 'deprecation_reason';
          transitionHandler(governanceAction.asset,governanceAction.action,{[key]:governanceEvidence.trim()});
        }}>
          <h2>{governanceAction.action.label}: {governanceAction.asset.name}</h2>
          <label>Evidence or reason<textarea required maxLength={2000} value={governanceEvidence} onChange={event => setGovernanceEvidence(event.target.value)} /></label>
          <button type="submit" disabled={!governanceEvidence.trim() || transitioningAssetIds.has(governanceAction.asset.asset_id)}>Confirm lifecycle change</button>
          <button type="button" disabled={transitioningAssetIds.has(governanceAction.asset.asset_id)} onClick={() => setGovernanceAction(null)}>Cancel</button>
        </form>
      </section>}
      <section className="depo-panel depo-panel--workspace">
        <div className="depo-panel__header">
          <div>
            <div className="depo-panel__title">Metadata Registry</div>
            <div className="depo-panel__meta">
              Governed catalog for definitions, ownership, lifecycle, versions, and physical implementations.
            </div>
          </div>
          <button type="button" className="depo-button depo-button--secondary" onClick={() => {
            fetchOntologies(); loadRegistryAssets();
            if (section === 'dictionary' && selectedOntology) loadDictionary(selectedOntology);
          }} disabled={loading || registryLoading || dictionaryLoading || createLoading || transitioningAssetIds.size > 0}>
            <RefreshCw size={14} className={loading ? 'depo-spin' : ''} />
            Refresh catalog
          </button>
        </div>
        <div className="depo-panel__body" style={{ display: 'grid', gap: 12 }}>
          {registryStale && <p role="status">Registry refresh failed. Retained rows may be stale; current counts are unavailable until refresh succeeds.</p>}
          <WorkspaceTabs label="Metadata registry views" tabs={[{id:'assets',label:'Registry assets'},{id:'dictionary',label:'Data Dictionary'}]} value={section} onChange={setSection} />

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
                <RegistryDictionaryTable nodes={dictionary} filter={dictionaryFilter} prefixFilter={prefixFilter} onPrefixFilterChange={setPrefixFilter}
                  disabled={createLoading || registryLoading || !registryLoaded} onRegister={node => {
                    try {
                      const source = ontologies.find(entry => entry.ontology_id === selectedOntology);
                      const proposed = dictionaryAssetDraft(node, source);
                      if (registryAssets.some(asset => asset.asset_id === proposed.asset_id)) throw new Error('This ontology term is already registered. Review its existing asset.');
                      setNewAsset(proposed); setSection('assets');
                      setRegistryMessage({ kind: 'success', text: 'Draft prepared from the ontology term. Review ownership and definition, then click Register. Nothing has been written yet.' });
                    } catch (failure) { setDictionaryError(failure.message); }
                  }} />
              )}
              {!selectedOntology && <div className="depo-empty">Select a registered source to inspect its terms, properties, and relationships.</div>}
            </div>
          )}

          {section === 'assets' && (
            <>
              <RegistrySummaryCards items={[
                { icon: <Database size={15} />, label: 'Governed assets on this page', value: registryLoaded ? registryAssets.length : '—' },
                { icon: <ShieldCheck size={15} />, label: 'Approved assets on this page', value: registryLoaded ? publishedCount : '—' },
                { icon: <Clock3 size={15} />, label: 'Review required on this page', value: registryLoaded ? reviewCount : '—' },
              ]} />
              <RegistryAssetsSection
                newAsset={newAsset}
                setNewAsset={setNewAsset}
                createAsset={createAsset}
                createLoading={createLoading}
                registryMessage={registryMessage}
                query={query}
                setQuery={setQuery}
                error={error}
                registryLoaded={registryLoaded}
                loading={loading}
                visibleRegistryAssets={visibleRegistryAssets}
                registryAssets={registryAssets}
                entries={entries}
                transitionHandler={transitionHandler}
                transitioningAssetIds={transitioningAssetIds}
                lastUpdated={lastUpdated}
              />
              <nav aria-label="Metadata asset pages">
                <p>Page {Math.floor(registryOffset / 1000) + 1}. Filters and counts apply to this page.</p>
                <button type="button" disabled={registryLoading || registryOffset === 0} onClick={() => loadRegistryAssets(Math.max(0, registryOffset - 1000))}>Previous asset page</button>
                <button type="button" disabled={registryLoading || !registryHasMore} onClick={() => loadRegistryAssets(registryOffset + 1000)}>Next asset page</button>
              </nav>
            </>
          )}
        </div>
      </section>
    </div>
  );
}
