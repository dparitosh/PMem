// Retained older results can contain resource identities in their name fields.
// This is presentation only: node/relationship IDs remain untouched.
export function businessDisplayName(value, fallback = 'Business name not recorded') {
  if (typeof value !== 'string' || !value.trim()) return fallback;
  let decoded = value.trim();
  try { decoded = decodeURIComponent(decodeURIComponent(decoded)); } catch { /* Keep malformed text for the checks below. */ }
  if (/^(?:https?:\/\/|urn:|scoped:|_:|[a-f0-9]{64}$|[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$|\d+:[a-f0-9-]{36}:\d+$|[A-Za-z]:[\\/])/i.test(decoded)
      || /^[{[<]/.test(decoded) || value.length > 2000) return fallback;
  return value.trim().slice(0, 250);
}

export function businessPathNames(item) {
  return (item.path_names || []).map(name => businessDisplayName(name));
}
