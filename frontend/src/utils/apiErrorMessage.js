// FastAPI validation details may be arrays of objects containing submitted
// input. Never render those objects or echo their input fields into the UI.
export function apiErrorMessage(error, fallback = 'Request failed.') {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) return 'Invalid request. Check the selected values and try again.';
  const message = error?.message;
  return typeof message === 'string' && message.trim() ? message : fallback;
}
