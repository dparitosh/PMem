// A server-issued run identity always takes precedence over an HTTP rejection.
export function confirmedSubmissionRejection(error) {
  const runId = error.response?.headers?.['x-depo-run-id'];
  return !runId && [400, 401, 403, 404, 405, 413, 415, 422, 429].includes(error.response?.status);
}
