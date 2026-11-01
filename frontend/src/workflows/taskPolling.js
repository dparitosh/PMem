// Access rejection needs reconnection, not a periodic retry storm. Transient
// read failures use a bounded backoff; this helper never resubmits an action.
export function taskPollDelay(error, failures = 0, interval = 15000) {
 const status = error?.response?.status;
 if ([401,403].includes(status)) return null;
 return error ? Math.min(60000, interval * 2 ** Math.min(3, Math.max(1, failures))) : interval;
}
