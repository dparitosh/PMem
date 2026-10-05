// FastAPI validation details may be arrays of objects containing submitted
// input. Never render those objects or echo their input fields into the UI.
export function apiErrorMessage(error, fallback = 'Request failed.') {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) return 'Invalid request. Check the selected values and try again.';
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
