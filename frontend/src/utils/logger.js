/**
 * Logger Utility - Environment-aware logging
 * Disables verbose logging in production, keeps it in development
 */

const isDevelopment = process.env.NODE_ENV === 'development';
const isVerboseLoggingEnabled = process.env.REACT_APP_VERBOSE_LOGS === 'true';
const canDebugLog = isDevelopment && isVerboseLoggingEnabled;

export const logger = {
  // Verbose logs are opt-in during development
  render: (...args) => {
    if (canDebugLog) console.log('[RENDER]', ...args);
  },

  data: (...args) => {
    if (canDebugLog) console.log('[DATA]', ...args);
  },

  search: (...args) => {
    if (canDebugLog) console.log('[SEARCH]', ...args);
  },

  sync: (...args) => {
    if (canDebugLog) console.log('[SYNC]', ...args);
  },

  api: (...args) => {
    if (canDebugLog) console.log('[API]', ...args);
  },

  ontology: (...args) => {
    if (canDebugLog) console.log('[ONTOLOGY]', ...args);
  },

  // Warnings are also opt-in for verbose local debugging
  warn: (...args) => {
    if (canDebugLog) console.warn('[WARN]', ...args);
  },

  // Errors remain visible
  error: (...args) => {
    console.error('[ERROR]', ...args);
  },

  // Performance measurement
  time: (label) => {
    if (canDebugLog) console.time(label);
  },

  timeEnd: (label) => {
    if (canDebugLog) console.timeEnd(label);
  },
};

export default logger;
