import { credentialServices } from '../services/credentialProfiles';
import React, { useState, useEffect } from 'react';
import { buildSemanticServiceUrl, config } from '../config';
import { getCredentialProfile, setCredentialProfile, clearServiceAuthToken, getGatewaySubscriptionKey, setGatewaySubscriptionKey, serviceAuthHeaders, setBrowserSessionExpiry, getBrowserSessionStatus } from '../services/serviceAuth';
import ServiceAccessDiscovery from '../app/ServiceAccessDiscovery';
import './CredentialSettings.css';

const profiles = Object.keys(credentialServices);
export default function CredentialSettings() {
  const [values, setValues] = useState(() => Object.fromEntries(profiles.map(p => [p, getCredentialProfile(p).startsWith('depo_session_') ? '' : getCredentialProfile(p)])));
  const [subscription, setSubscription] = useState(getGatewaySubscriptionKey);
  const [results, setResults] = useState({});
  const [busy, setBusy] = useState(false);
  const [clearVersion, setClearVersion] = useState(0);
  const [actor, setActor] = useState('');
  const [expiry, setExpiry] = useState('');
  const [sessionAdminKey, setSessionAdminKey] = useState(() => getCredentialProfile('ADMIN_API_KEY'));
  const [includeWrites, setIncludeWrites] = useState(() => (getBrowserSessionStatus()?.profiles.length || 0) > 1);
  const [sessionStatus, setSessionStatus] = useState(() => {
    const session = getBrowserSessionStatus();
    return session ? `Session restored: ${session.profiles.length} delegated scopes. Expires ${new Date(session.expiresAt).toLocaleTimeString()}. Services verify access on each request.` : '';
  });
  useEffect(() => {
    const expired = () => { setSessionStatus('Central session expired or was rejected. Reconnect here; no operation was automatically retried.'); setResults({}); };
    window.addEventListener('depo:session-expired', expired);
    return () => window.removeEventListener('depo:session-expired', expired);
  }, []);
  async function connectCentralSession() {
    setBusy(true);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    const previousSubscription = getGatewaySubscriptionKey();
    let pendingSession = null;
    let sessionUrl = '';
    try {
      const url = buildSemanticServiceUrl('ontology', '/auth/browser-session');
      sessionUrl = url;
      const headers = { ...serviceAuthHeaders(url, 'post', subscription), 'Content-Type': 'application/json', 'X-API-Key': sessionAdminKey.trim() };
      delete headers.Authorization;
      const response = await fetch(url, { method: 'POST', headers, body: JSON.stringify({ include_writes: includeWrites }), signal: controller.signal, credentials: 'omit', redirect: 'error' });
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof body.detail === 'string' ? body.detail : `Connection failed (${response.status})`);
      if (!body.token?.startsWith('depo_session_') || !Array.isArray(body.profiles) || !body.profiles.includes('GRAPH_READ_TOKEN') || !body.expires_at) throw new Error('Invalid central session response');
      pendingSession = body.token;
      if (!Number.isFinite(Date.parse(body.expires_at)) || Date.parse(body.expires_at) <= Date.now()) throw new Error('Central session is already expired; check application and database VM clocks.');
      const services = Object.keys(config.semanticServiceUrls).filter(service => config.semanticServiceUrls[service]);
      const checks = await Promise.allSettled(services.map(async service => {
        const endpoint = buildSemanticServiceUrl(service, '/auth/access');
        const probe = await fetch(endpoint, { headers: { ...serviceAuthHeaders(endpoint, 'get', subscription), Authorization: `Bearer ${body.token}` }, signal: controller.signal, credentials: 'omit', redirect: 'error' });
        const result = await probe.json().catch(() => ({}));
        if (!probe.ok || result.status !== 'authorized') throw new Error(`${service}: HTTP ${probe.status}; central session was not accepted`);
      }));
      if (!checks.length) throw new Error('No service endpoints are configured');
      const failures = checks.flatMap((check, index) => check.status === 'rejected' ? [`${services[index]}: ${check.reason?.name === 'AbortError' ? 'timed out' : check.reason?.message || 'transport failure'}`] : []);
      if (failures.length) throw new Error(`Connection checks failed: ${failures.join('; ')}. Previous browser access was preserved. Check service listeners, routing and credential-store configuration.`);
      clearServiceAuthToken();
      setGatewaySubscriptionKey(subscription);
      body.profiles.filter(profile => profiles.includes(profile) && profile !== 'ADMIN_API_KEY').forEach(profile => setCredentialProfile(profile, body.token));
      setBrowserSessionExpiry(body.token, body.expires_at);
      pendingSession = null;
      setValues(Object.fromEntries(profiles.map(profile => [profile, ''])));
      setResults(Object.fromEntries(body.profiles.map(profile => [profile, `Connected via central session until ${new Date(body.expires_at).toLocaleTimeString()}`])));
      setSessionAdminKey('');
      setSessionStatus(`Connected ${body.profiles.length} registered scopes. Session expires ${new Date(body.expires_at).toLocaleTimeString()}. Credential administration still requires the separate admin key.`);
      window.dispatchEvent(new Event('depo:credentials-changed'));
    } catch (error) {
      if (pendingSession && sessionUrl) {
        const cleanup = new AbortController();
        const cleanupTimeout = setTimeout(() => cleanup.abort(), 5000);
        try { await fetch(sessionUrl, { method: 'DELETE', headers: { ...serviceAuthHeaders(sessionUrl, 'delete', subscription), Authorization: `Bearer ${pendingSession}` }, signal: cleanup.signal, credentials: 'omit', redirect: 'error' }); }
        catch { /* An unreachable abandoned session expires server-side. */ }
        finally { clearTimeout(cleanupTimeout); }
      }
      setGatewaySubscriptionKey(previousSubscription);
      setSessionStatus(error.name === 'AbortError' ? 'Connection timed out; check service connectivity.' : error.message);
    } finally { clearTimeout(timeout); setBusy(false); }
  }
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
      if (profile === 'ADMIN_API_KEY') {
        setSessionAdminKey(key);
        setSessionStatus('Administrator key validated. Click Connect registered services above to enable service reads; enable workflow scopes for uploads and execution.');
      }
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
    <div className="depo-panel depo-central-session">
      <h3>Connect registered service credentials</h3>
      <p>After the PowerShell import succeeds, enter ADMIN_API_KEY once here. A fifteen-minute delegated session authorizes registered scopes without copying their keys into this browser. The session survives refresh in this tab when browser session storage is available. Clear, rotation, revocation or expiry invalidates access. Raw API keys remain memory-only.</p>
      <label>Administrator key for connection<input aria-label="Administrator key for connection" type="password" autoComplete="off" disabled={busy} value={sessionAdminKey} onChange={event => setSessionAdminKey(event.target.value)} /></label>
      <label><input type="checkbox" disabled={busy} checked={includeWrites} onChange={event => setIncludeWrites(event.target.checked)} /> Enable registered upload, execution and approval scopes for this session</label>
      <button type="button" disabled={busy || !sessionAdminKey.trim()} onClick={connectCentralSession}>Connect registered services</button>
      <p role="status">{sessionStatus || 'Read-only by default. Enable workflow scopes only when required. No jobs run during connection.'}</p>
    </div>
    <p>All application API-key profiles are listed here, even before OpenAPI import. Database passwords, Neo4j credentials and outbound integration tokens remain in server configuration; they are never exposed to the browser.</p>
    <p>Use Connect registered services above to apply centrally registered scopes. Testing ADMIN_API_KEY in this table validates administrator access only; it does not sign in to graph, catalog, products or observability. Individual keys below are an alternative. Keys remain in this tab only and are cleared by a full reload.</p>
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
      </div></td><td><span role="status">{results[profile] || (getCredentialProfile(profile)?.startsWith('depo_session_') ? 'Central session stored; reconnect if expired' : getCredentialProfile(profile) ? 'Key stored; test to verify' : 'Not entered in this browser')}</span></td>
    </tr>)}</tbody></table></div>
    <button type="button" disabled={busy} onClick={async () => {
      const token = getCredentialProfile('GRAPH_READ_TOKEN');
      if (token?.startsWith('depo_session_')) {
        const url = buildSemanticServiceUrl('ontology', '/auth/browser-session');
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 5000);
        try { await fetch(url, { method: 'DELETE', headers: { ...serviceAuthHeaders(url, 'delete'), Authorization: `Bearer ${token}` }, signal: controller.signal, credentials: 'omit', redirect: 'error' }); }
        catch { /* Memory is cleared even when logout cannot reach the server. */ }
        finally { clearTimeout(timeout); }
      }
      clearServiceAuthToken(); setValues(Object.fromEntries(profiles.map(p => [p, '']))); setSubscription(''); setResults({}); setSessionStatus('Browser access cleared.'); setSessionAdminKey(''); setClearVersion(v => v + 1);
    }}>Clear credentials</button>
    <ServiceAccessDiscovery key={clearVersion} subscriptionKey={subscription} excludedProfiles={profiles} />
  </section>;
}
