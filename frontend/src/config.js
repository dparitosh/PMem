// API Configuration
// Update these URLs to match your backend deployment

const config = {
  apiUrl: process.env.REACT_APP_BACKEND_URL || 'http://localhost:8000',
};

if (!process.env.REACT_APP_BACKEND_URL) {
  // eslint-disable-next-line no-console
  console.warn('Missing frontend env config. Using defaults. Check frontend/.env');
}

export default config;
