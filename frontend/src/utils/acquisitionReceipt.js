// Validate retained acquisition evidence before replacing recoverable browser state.
export function acquisitionRun(data, {runId, submissionId} = {}) {
  if (!data || typeof data !== 'object' || Array.isArray(data) ||
      (data.submission_id != null && data.submission_id !== submissionId)) {
    throw new Error('Acquisition receipt does not match the saved submission. Refresh retained state before retrying.');
  }
  const run = data.run_manifest || data.run || data;
  if (!run || typeof run.run_id !== 'string' || !run.run_id.trim() ||
      typeof run.status !== 'string' || !run.status.trim() ||
      (runId && run.run_id !== runId) ||
      (data.status != null && data.status !== run.status)) {
    throw new Error('Acquisition run was not confirmed. The saved submission is preserved; inspect retained state before retrying.');
  }
  return run;
}

// Browser coordination is advisory; backend receipts/locks remain authoritative.
export function checkAcquisitionReference(storageKey, expectedKey) {
  const raw = localStorage.getItem(storageKey);
  let current = null;
  if (raw !== null) {
    try { current = JSON.parse(raw); } catch { throw new Error('Saved acquisition reference is invalid. Inspect retained runs before starting another.'); }
    if (!current || typeof current.key !== 'string' || !current.key) {
      throw new Error('Saved acquisition reference is invalid. Inspect retained runs before starting another.');
    }
  }
  if ((current?.key ?? null) !== expectedKey) {
    throw new Error('The saved acquisition changed in another tab. Refresh its retained state before continuing.');
  }
  return current;
}

export function retainAcquisition(storageKey, value, expectedKey = value.key) {
  checkAcquisitionReference(storageKey, expectedKey);
  localStorage.setItem(storageKey, JSON.stringify(value));
}

export function clearAcquisition(storageKey, expectedKey) {
  checkAcquisitionReference(storageKey, expectedKey);
  localStorage.removeItem(storageKey);
}
