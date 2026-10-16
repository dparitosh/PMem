// FastAPI validation details may be arrays of objects containing submitted
// input. Never render those objects or echo their input fields into the UI.
export function apiRequestId(error) {
  const headers = error?.response?.headers;
  const value = headers?.get?.('X-Request-ID') || headers?.['x-request-id'] || headers?.['X-Request-ID'] || error?.response?.data?.request_id || error?.apiError?.requestId;
  return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$/.test(value) ? value : '';
}

export function apiErrorMessage(error, fallback = 'Request failed.') {
  return withApiRequestId(serviceMessage(error, fallback), error);
}

export function withApiRequestId(message, error) {
  const id = apiRequestId(error);
  return id && !message.includes(`Request ID: ${id}`) ? `${message} Request ID: ${id}` : message;
}

function serviceMessage(error, fallback) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) return 'Invalid request. Check the selected values and try again.';
  if (typeof detail?.message === 'string' && detail.message.trim()) return detail.message;
  const status = error?.response?.status;
  if (status === 401) return 'Authentication expired or is missing. Reconnect in Admin → Service credentials.';
  if (status === 403) return 'This operation lacks a valid credential scope. Test the required profile in Admin.';
  if (status === 404) return 'The requested artifact or API route was not found. Check the selected ontology and matching service release.';
  if (status === 503) return 'The service or a required dependency is unavailable. Check Admin service diagnostics and server logs.';
  if (status >= 500) return 'The service failed while processing this request. Check its server logs.';
  if (error?.code === 'ECONNABORTED' || error?.code === 'ETIMEDOUT') return 'The request timed out. Refresh operation status before retrying a write.';
  if (error?.code === 'ERR_NETWORK') return 'No usable service response. Check service listeners, network access and CORS configuration.';
  const message = error?.message;
  return typeof message === 'string' && message.trim() ? message : fallback;
}
