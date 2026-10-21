import React, { useEffect, useState } from 'react';
import { getBrowserSessionStatus, installBrowserSession, renewBrowserSession } from '../services/serviceAuth';

const DISCONNECTED = 'depo.localAccessDisconnected';

export default function BrowserAccessBoundary({ children }) {
  const [ready, setReady] = useState(false);
  const [mode, setMode] = useState('manual');
  const [message, setMessage] = useState('');
  const [connecting, setConnecting] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let stopped = false;
    let cancelled = false;
    let inFlight = false;
    let local = false;
    let timer;
    let recoveryTimer;
    let generation = 0;
    const controller = new AbortController();
    const fetchLocal = async (path, options = {}) => {
      const attempt = new AbortController();
      const abort = () => attempt.abort();
      controller.signal.addEventListener('abort', abort);
      const timeout = setTimeout(abort, 20000);
      try {
        const response = await fetch(path, { credentials:'same-origin', redirect:'error', ...options, signal:attempt.signal });
        const body = await response.json();
        if (attempt.signal.aborted) throw new Error('Local access request timed out or was cancelled.');
        return { ok: response.ok, body };
      }
      finally { clearTimeout(timeout); controller.signal.removeEventListener('abort', abort); }
    };
    const disconnected = () => {
      stopped = true; generation += 1;
      try { sessionStorage.setItem(DISCONNECTED, 'true'); } catch { /* Memory-only logout still applies. */ }
      if (local) setMessage('Local access is disconnected.');
    };
    const connect = async () => {
      if (inFlight || stopped || cancelled) return;
      inFlight = true; setConnecting(true);
      const version = generation;
      try {
        const response = await fetchLocal('/_pmem-local/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
        const body = response.body;
        if (!response.ok) throw new Error(body.detail || 'Local access could not connect.');
        if (!cancelled && !stopped && version === generation) {
          installBrowserSession(body);
          window.dispatchEvent(new Event('depo:credentials-changed'));
          setMessage('');
        }
      } catch (error) {
        if (!cancelled && !stopped && version === generation) setMessage(error.message || 'Local access could not connect.');
      } finally { inFlight = false; if (!cancelled) setConnecting(false); }
    };
    const keepAlive = async () => {
      if (!local || cancelled || stopped || inFlight || document.visibilityState === 'hidden') return;
      const current = getBrowserSessionStatus();
      if (!current) return connect();
      if (Date.parse(current.expiresAt) - Date.now() > 120000) return;
      inFlight = true;
      const version = generation;
      try { await renewBrowserSession(); if (!cancelled && !stopped && version === generation) setMessage(''); }
      catch { if (!cancelled && !stopped && version === generation) setMessage('Local session renewal failed. Reconnect local access or check service credentials.'); }
      finally { inFlight = false; }
    };
    const initialize = async () => {
      try {
        const response = await fetchLocal('/_pmem-local/config');
        if (!response.ok) return; // Existing static/distributed servers retain manual authentication.
        const config = response.body;
        if (cancelled || config.mode !== 'local') return;
        local = true; setMode('local');
        try { stopped = sessionStorage.getItem(DISCONNECTED) === 'true'; } catch { /* Optional storage. */ }
        if (stopped) setMessage('Local access is disconnected.');
        else await connect();
        if (!cancelled) timer = setInterval(keepAlive, 30000);
      } catch { /* Manual access stays available if the launcher is absent. */ }
      finally { if (!cancelled) setReady(true); }
    };
    const recoverExpired = () => {
      if (!local || stopped || cancelled) return;
      clearTimeout(recoveryTimer);
      // Renewal rejection can emit this while a request is still unwinding.
      // Recover on the next turn without replaying any failed API operation.
      recoveryTimer = setTimeout(keepAlive, 0);
    };
    window.addEventListener('depo:credentials-cleared', disconnected);
    window.addEventListener('depo:session-expired', recoverExpired);
    document.addEventListener('visibilitychange', keepAlive);
    initialize();
    return () => {
      cancelled = true; generation += 1; controller.abort(); clearInterval(timer); clearTimeout(recoveryTimer);
      window.removeEventListener('depo:credentials-cleared', disconnected);
      window.removeEventListener('depo:session-expired', recoverExpired);
      document.removeEventListener('visibilitychange', keepAlive);
    };
  }, [retry]);
  if (!ready) return <p role="status">Connecting application access…</p>;
  return <>{mode === 'local' && message && <div role="status" style={{padding:'8px 12px',borderBottom:'1px solid var(--ui-border,#d5dfe9)',fontSize:12}}>{message} <button type="button" disabled={connecting} onClick={() => {
    try { sessionStorage.removeItem(DISCONNECTED); } catch { /* Storage is optional. */ }
    setRetry(value => value + 1);
  }}>{connecting ? 'Connecting…' : 'Reconnect local access'}</button></div>}{children}</>;
}
