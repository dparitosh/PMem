export function applyRequestDeadline(request) {
  const now = Date.now();
  if (!Number.isFinite(request.__deadlineAt)) {
    const timeout = Number(request.timeout);
    if (Number.isFinite(timeout) && timeout > 0) request.__deadlineAt = now + timeout;
  }
  if (Number.isFinite(request.__deadlineAt)) {
    const remaining = request.__deadlineAt - now;
    if (remaining <= 0) {
      const error = new Error('Request deadline exceeded');
      error.code = 'ECONNABORTED';
      error.config = request;
      throw error;
    }
    request.timeout = remaining;
  }
  return request;
}
export function abortableDelay(ms, signal) {
  return new Promise((resolve, reject) => {
    const aborted = () => { clearTimeout(timer); signal?.removeEventListener('abort', aborted); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = setTimeout(() => { signal?.removeEventListener('abort', aborted); resolve(); }, ms);
    if (signal?.aborted) aborted();
    else signal?.addEventListener('abort', aborted, { once: true });
  });
}
export function retryFitsDeadline(request, delay) {
  return !request.signal?.aborted && (!Number.isFinite(request.__deadlineAt) || Date.now() + delay < request.__deadlineAt);
}
