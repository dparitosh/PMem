// API Configuration
// Update these URLs to match your backend deployment

const browserHost = typeof window !== 'undefined' && window.location?.hostname
  ? window.location.hostname
  : '127.0.0.1';
const defaultBackendUrl = `http://${browserHost}:8000`;

const config = {
  apiUrl: process.env.REACT_APP_BACKEND_URL || defaultBackendUrl,
  neo4jUrl: process.env.REACT_APP_NEO4J_URL || 'bolt://127.0.0.1:7687',
};

if (!process.env.REACT_APP_BACKEND_URL || !process.env.REACT_APP_NEO4J_URL) {
  // eslint-disable-next-line no-console
  console.warn('Missing frontend env config. Using defaults. Check frontend/.env');
}

export default config;
