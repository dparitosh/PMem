import React, { useState } from 'react';
import { config } from '../config';
import { discoverServices } from '../services/serviceDiscovery';
import { getCredentialProfile, setCredentialProfile } from '../services/serviceAuth';
export default function ServiceAccessDiscovery({ subscriptionKey, excludedProfiles = [] }) {
  const [results, setResults] = useState([]);
  const [busy, setBusy] = useState(false);
  const profiles = [...new Set(results.flatMap(result => result.profiles || []))].filter(profile => profile !== 'GRAPH_READ_TOKEN' && !excludedProfiles.includes(profile));
  return <section aria-label="OpenAPI service discovery">
    <p>Import contracts to discover service operations and their required credential profiles. Import success does not verify API keys or graph access. Secret values are never imported. Entering a profile key stores it in this tab until Clear or reload; its validity is checked by the service when used.</p>
    <button type="button" disabled={busy} onClick={async () => {
      setBusy(true);
      try { setResults(await discoverServices(config.semanticServiceUrls, fetch, subscriptionKey)); } finally { setBusy(false); }
    }}>{busy ? 'Importing contracts...' : 'Import service OpenAPI contracts'}</button>
    <ul>{results.map(result => <li key={result.service}>{result.service}: {result.status === 'imported' ? `${result.operationCount} operations imported` : result.message}</li>)}</ul>
    {profiles.map(profile => <label key={profile} style={{ display: 'block' }}>{profile}
      <input type="password" autoComplete="off" defaultValue={getCredentialProfile(profile)} onChange={event => setCredentialProfile(profile, event.target.value)} />
    </label>)}
    {profiles.length > 0 && <p>Operation-specific credentials take precedence over the read key. Explicit credentials entered on a workflow page take precedence over discovered profiles.</p>}
  </section>;
}
