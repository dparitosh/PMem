import { useCallback, useEffect, useState } from 'react';

// One URL-backed view value; preserve the owning page's deep-link parameters.
const NO_ALIASES = {};
export default function useRouteView(allowed, fallback, aliases = NO_ALIASES, route = '#/data-flow', queryKey = 'view') {
  const read = () => {
    const value = new URLSearchParams(window.location.hash.split('?')[1] || '').get(queryKey);
    const canonical=aliases[value]||value;
    return allowed.includes(canonical) ? canonical : (typeof fallback==='function'?fallback():fallback);
  };
  const [view, setView] = useState(read);
  useEffect(() => {
    const changed = () => setView(read());
    window.addEventListener('hashchange', changed);
    window.addEventListener('popstate', changed);
    return () => { window.removeEventListener('hashchange', changed); window.removeEventListener('popstate', changed); };
  }, [allowed, fallback, aliases, queryKey]);
  const navigate = useCallback(next => {
    if (!allowed.includes(next)) return;
    const [path, search = ''] = window.location.hash.split('?');
    const params = new URLSearchParams(search);
    params.set(queryKey, next);
    if(queryKey==='view'&&next!=='analytics') params.delete('analytics_step');
    const hash = `${path && path!=='#/'?path:route}?${params}`;
    if (window.location.hash !== hash) {
      window.history.pushState(null, '', hash);
      window.dispatchEvent(new HashChangeEvent('hashchange'));
    }
    setView(next);
  }, [allowed, route, queryKey]);
  return [view, navigate, setView];
}
