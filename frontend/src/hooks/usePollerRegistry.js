import { useCallback, useEffect, useRef } from 'react';

export default function usePollerRegistry(isMountedRef) {
  const activePollersRef = useRef(new Set());
  const pollerTimersRef = useRef(new Map());

  const clearPoller = useCallback((pollerKey) => {
    const timerId = pollerTimersRef.current.get(pollerKey);
    if (timerId) {
      clearTimeout(timerId);
      pollerTimersRef.current.delete(pollerKey);
    }
    activePollersRef.current.delete(pollerKey);
  }, []);

  const schedulePoller = useCallback((pollerKey, callback, delayMs) => {
    const existingTimer = pollerTimersRef.current.get(pollerKey);
    if (existingTimer) {
      clearTimeout(existingTimer);
    }

    const timerId = setTimeout(() => {
      pollerTimersRef.current.delete(pollerKey);
      if (!isMountedRef.current || !activePollersRef.current.has(pollerKey)) {
        clearPoller(pollerKey);
        return;
      }
      callback();
    }, delayMs);

    pollerTimersRef.current.set(pollerKey, timerId);
  }, [clearPoller, isMountedRef]);

  useEffect(() => () => {
    pollerTimersRef.current.forEach((timerId) => clearTimeout(timerId));
    pollerTimersRef.current.clear();
    activePollersRef.current.clear();
  }, []);

  return {
    activePollersRef,
    clearPoller,
    pollerTimersRef,
    schedulePoller,
  };
}
