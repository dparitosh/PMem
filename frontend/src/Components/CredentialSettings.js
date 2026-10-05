import { credentialServices } from '../services/credentialProfiles';
import React, { useState } from 'react';
import { buildSemanticServiceUrl, config } from '../config';
import { getCredentialProfile, setCredentialProfile, clearServiceAuthToken, getGatewaySubscriptionKey, setGatewaySubscriptionKey, serviceAuthHeaders } from '../services/serviceAuth';
import ServiceAccessDiscovery from '../app/ServiceAccessDiscovery';
import './CredentialSettings.css';

const profiles = Object.keys(credentialServices);
export default function CredentialSettings() {
  const [values, setValues] = useState(() => Object.fromEntries(profiles.map(p => [p, getCredentialProfile(p)])));
  const [subscription, setSubscription] = useState(getGatewaySubscriptionKey);
  const [results, setResults] = useState({});
  const [busy, setBusy] = useState(false);
  const [clearVersion, setClearVersion] = useState(0);
  const [actor, setActor] = useState('');
  const [expiry, setExpiry] = useState('');
  async function validate(profile) {
    setBusy(true);
    const key = values[profile].trim();
    const previousSubscription = getGatewaySubscriptionKey();
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      setGatewaySubscriptionKey(subscription);
      const services = profile === 'GRAPH_READ_TOKEN' ? Object.keys(config.semanticServiceUrls) : [credentialServices[profile]];
      const checks = await Promise.all(services.map(async service => {
        try {
          const url = buildSemanticServiceUrl(service, profile === 'GRAPH_READ_TOKEN' ? '/auth/access' : profile === 'ADMIN_API_KEY' ? '/auth/admin-access' : `/auth/credential-check?profile=${profile}`);
          const headers = { ...serviceAuthHeaders(url) };
          delete headers.Authorization; delete headers['X-API-Key'];
          headers[profile === 'ADMIN_API_KEY' ? 'X-API-Key' : 'Authorization'] = profile === 'ADMIN_API_KEY' ? key : `Bearer ${key}`;
          const response = await fetch(url, { headers, signal: controller.signal, credentials: 'omit', redirect: 'error' });
          const body = await response.json().catch(() => ({}));
          if (!response.ok || body.status !== 'authorized') throw new Error(typeof body.detail === 'string' ? body.detail : `HTTP ${response.status}`);
          return { service, valid: true };
        } catch (error) { return { service, valid: false, message: error.message }; }
      }));
      if (!checks.length || checks.some(check => !check.valid)) throw new Error(checks.map(check => `${check.service}: ${check.valid ? 'authorized' : check.message}`).join('; ') || 'No services configured');
      setCredentialProfile(profile, key);
      setResults(prev => ({ ...prev, [profile]: `Validated and applied: ${checks.map(check => check.service).join(', ')}` }));
      window.dispatchEvent(new Event('depo:credentials-changed'));
    } catch (error) {
      setGatewaySubscriptionKey(previousSubscription);
      setResults(prev => ({ ...prev, [profile]: error.name === 'AbortError' ? 'Validation timed out; check service connectivity.' : error.message }));
    }
    finally { clearTimeout(timeout); setBusy(false); }
  }
  async function register(profile) {
    if (!window.confirm(`Register or rotate ${profile} in PostgreSQL? Existing keys for this profile will stop working.`)) return;
    setBusy(true);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const url = buildSemanticServiceUrl('ontology', `/auth/credentials/${profile}`);
      const headers = { ...serviceAuthHeaders(url), 'Content-Type': 'application/json', 'X-API-Key': getCredentialProfile('ADMIN_API_KEY') };
      delete headers.Authorization;
      const response = await fetch(url, { method: 'POST', headers, body: JSON.stringify({ key: values[profile].trim(), actor: actor.trim(), expires_at: expiry.trim() || null }), signal: controller.signal, credentials: 'omit', redirect: 'error' });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Registration failed (${response.status}); test the key before retrying`);
      setCredentialProfile(profile, values[profile]);
      setResults(prev => ({ ...prev, [profile]: 'Registered centrally and applied. Backend outbound keys must also be updated after rotation.' }));
      window.dispatchEvent(new Event('depo:credentials-changed'));
    } catch (error) { setResults(prev => ({ ...prev, [profile]: `${error.message}. If the response was lost, test the new key before rotating again.` })); }
    finally { clearTimeout(timeout); setBusy(false); }
  }
  async function revoke(profile) {
    if (!window.confirm(`Revoke ${profile}? Calls using this key will be rejected immediately.`)) return;
    setBusy(true);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const url = buildSemanticServiceUrl('ontology', `/auth/credentials/${profile}`);
      const headers = { ...serviceAuthHeaders(url), 'X-API-Key': getCredentialProfile('ADMIN_API_KEY') };
      delete headers.Authorization;
      const response = await fetch(url, { method: 'DELETE', headers, signal: controller.signal, credentials: 'omit', redirect: 'error' });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Revocation failed (${response.status})`);
      setCredentialProfile(profile, '');
      setValues(prev => ({ ...prev, [profile]: '' }));
      setResults(prev => ({ ...prev, [profile]: 'Revoked centrally' }));
      window.dispatchEvent(new Event('depo:credentials-changed'));
    } catch (error) { setResults(prev => ({ ...prev, [profile]: error.message })); }
    finally { clearTimeout(timeout); setBusy(false); }
  }
  return <section className="depo-panel" aria-label="Service credentials">
    <h2>Service credentials</h2>
    <p>All application API-key profiles are listed here, even before OpenAPI import. Database passwords, Neo4j credentials and outbound integration tokens remain in server configuration; they are never exposed to the browser.</p>
    <p>Enter administrator-issued keys here. Read access uses GRAPH_READ_TOKEN; ontology uploads use INGESTION_WRITE_TOKEN; governed instance jobs use DATA_JOB_EXECUTION_TOKEN. Validation checks authentication without running a job. Keys remain in this tab only and are cleared by a full reload.</p>
    <div className="depo-credential-controls"><label>APIM subscription key (optional)<input type="password" autoComplete="off" disabled={busy} value={subscription} onChange={e => setSubscription(e.target.value)} /></label>
    <label>Assigned actor for registration<input disabled={busy} value={actor} onChange={e => setActor(e.target.value)} /></label>
    <label>Optional expiry (UTC ISO timestamp, e.g. 2027-01-01T00:00:00Z)<input disabled={busy} value={expiry} onChange={e => setExpiry(e.target.value)} /></label>
    </div>
    <div className="depo-credential-table-scroll"><table className="depo-credential-table">
      <caption>Application keys and validation results</caption>
      <thead><tr><th scope="col">Credential profile</th><th scope="col">Service</th><th scope="col">API key</th><th scope="col">Actions</th><th scope="col">Status</th></tr></thead>
      <tbody>{profiles.map(profile => <tr key={profile}>
      <th scope="row">{profile}</th><td>{credentialServices[profile]}</td><td>
      <input aria-label={profile} type="password" autoComplete="off" disabled={busy} value={values[profile]} onChange={e => { setValues(prev => ({ ...prev, [profile]: e.target.value })); setResults(prev => ({ ...prev, [profile]: '' })); }} /></td>
      <td><div className="depo-credential-actions">
      <button type="button" disabled={busy || !values[profile].trim()} onClick={() => validate(profile)}>Test and apply</button>
      <button type="button" disabled={busy || values[profile].trim().length < 32 || !actor.trim() || !getCredentialProfile('ADMIN_API_KEY')} onClick={() => register(profile)}>Register / rotate in database</button>
      {profile !== 'ADMIN_API_KEY' && <button type="button" disabled={busy || !getCredentialProfile('ADMIN_API_KEY')} onClick={() => revoke(profile)}>Revoke in database</button>}
      </div></td><td><span role="status">{results[profile] || (getCredentialProfile(profile) ? 'Key stored; test to verify' : 'Not configured')}</span></td>
    </tr>)}</tbody></table></div>
    <button type="button" disabled={busy} onClick={() => { clearServiceAuthToken(); setValues(Object.fromEntries(profiles.map(p => [p, '']))); setSubscription(''); setResults({}); setClearVersion(v => v + 1); }}>Clear credentials</button>
    <ServiceAccessDiscovery key={clearVersion} subscriptionKey={subscription} excludedProfiles={profiles} />
  </section>;
}
