/**
 * Logger Utility - Environment-aware logging
 * Disables verbose logging in production, keeps it in development
 */

const isDevelopment = process.env.NODE_ENV === 'development';

export const logger = {
  // Development-only logs (disabled in production)
  render: (...args) => {
    if (isDevelopment) console.log('[RENDER]', ...args);
  },

  data: (...args) => {
    if (isDevelopment) console.log('[DATA]', ...args);
  },

  search: (...args) => {
    if (isDevelopment) console.log('[SEARCH]', ...args);
  },

  sync: (...args) => {
    if (isDevelopment) console.log('[SYNC]', ...args);
  },

  api: (...args) => {
    if (isDevelopment) console.log('[API]', ...args);
  },

  ontology: (...args) => {
    if (isDevelopment) console.log('[ONTOLOGY]', ...args);
  },

  // Always logged
  warn: (...args) => {
    console.warn('[WARN]', ...args);
  },

  error: (...args) => {
    console.error('[ERROR]', ...args);
  },

  // Performance measurement
  time: (label) => {
    if (isDevelopment) console.time(label);
  },

  timeEnd: (label) => {
    if (isDevelopment) console.timeEnd(label);
  },
};

export default logger;
