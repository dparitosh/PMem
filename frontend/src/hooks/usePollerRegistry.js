import { useCallback, useEffect, useRef } from 'react';

export default function usePollerRegistry(isMountedRef) {
  const activePollersRef = useRef(new Set());
  const pollerTimersRef = useRef(new Map());
  const pollerControllersRef = useRef(new Map());

  const clearPoller = useCallback((pollerKey) => {
    const timerId = pollerTimersRef.current.get(pollerKey);
    if (timerId) {
      clearTimeout(timerId);
      pollerTimersRef.current.delete(pollerKey);
    }
    const controller = pollerControllersRef.current.get(pollerKey);
    controller?.abort();
    pollerControllersRef.current.delete(pollerKey);
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
      const controller = new AbortController();
      pollerControllersRef.current.set(pollerKey, controller);
      Promise.resolve(callback(controller.signal)).catch(() => {}).finally(() => {
        if (pollerControllersRef.current.get(pollerKey) === controller) {
          pollerControllersRef.current.delete(pollerKey);
        }
      });
    }, delayMs);

    pollerTimersRef.current.set(pollerKey, timerId);
  }, [clearPoller, isMountedRef]);

  useEffect(() => () => {
    pollerTimersRef.current.forEach((timerId) => clearTimeout(timerId));
    pollerControllersRef.current.forEach((controller) => controller.abort());
    pollerTimersRef.current.clear();
    pollerControllersRef.current.clear();
    activePollersRef.current.clear();
  }, []);

  return {
    activePollersRef,
    clearPoller,
    pollerTimersRef,
    schedulePoller,
  };
}
