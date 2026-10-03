import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { buildReceiptPlugin } from './buildReceipt.mjs';

export default defineConfig(({ mode }) => {
  // The application was migrated from CRA.  Vite exposes only VITE_* values
  // by default, while the existing customer deployment files use REACT_APP_*.
  // Load both prefixes explicitly and compile only browser-safe UI settings.
  const loaded = loadEnv(mode, process.cwd(), '');
  const credentialSetting = (key) => /(?:^|_)(?:TOKEN|API_?KEY|PASSWORD|SECRET|PRIVATE_?KEY|SUBSCRIPTION_?KEY)(?:_|$)/i.test(key);
  const forbiddenSettings = Object.keys({ ...loaded, ...process.env }).filter(key =>
    (key.startsWith('VITE_') || key.startsWith('REACT_APP_')) && credentialSetting(key));
  if (forbiddenSettings.length) {
    throw new Error(`Browser credential settings are forbidden: ${forbiddenSettings.join(', ')}. Remove them from frontend environment configuration; enter credentials through API access.`);
  }
  const isPublicClientSetting = (key) => {
    if (!(key.startsWith('VITE_') || key.startsWith('REACT_APP_') || key === 'HOST')) return false;
    // Vite values are compiled into JavaScript and can be read by every browser
    // user. Authentication material belongs in the gateway or in a one-time,
    // in-memory approval field, never in an environment value compiled here.
    return !credentialSetting(key);
  };
  const clientEnv = Object.fromEntries(
    Object.entries({ ...loaded, ...process.env }).filter(([key]) => isPublicClientSetting(key)),
  );

  for (const [key, value] of Object.entries(clientEnv)) {
    if (key.startsWith('VITE_')) {
      const alias = `REACT_APP_${key.slice(5)}`;
      if (Object.prototype.hasOwnProperty.call(clientEnv, alias) && clientEnv[alias] !== value) {
        throw new Error(`Conflicting browser settings: ${key} and ${alias}. Keep one setting or make their values identical.`);
      }
    }
  }

  return {
    plugins: [react(), buildReceiptPlugin(process.cwd())],
    define: {
      'process.env': JSON.stringify(clientEnv),
    },
    server: { host: '127.0.0.1', port: 3000, strictPort: true },
    esbuild: {
      loader: 'jsx',
      include: /src\/.*\.js$/,
      exclude: [],
    },
    optimizeDeps: {
      esbuildOptions: {
        loader: { '.js': 'jsx' },
      },
    },
    build: {
      rollupOptions: {
        output: {
          // Cache graph/grid dependencies independently. Leave IX to Rollup's
          // automatic chunking and tree shaking; forcing the entire package
          // into one manual chunk retains unused components. Feature pages
          // remain lazy through the route registry.
          manualChunks(id) {
            if (!id.includes('node_modules')) return undefined;
            // Let Rollup follow IX's component imports and lazy boundaries.
            // A single manual IX chunk pulls deferred components into startup.
            if (id.includes('@siemens')) return undefined;
            if (id.includes('ag-grid')) return 'vendor-data-grid';
            if (id.includes('@xyflow') || id.includes('/d3')) return 'vendor-graph';
            if (id.includes('react') || id.includes('scheduler')) return 'vendor-react';
            return 'vendor-core';
          },
        },
      },
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/setupTests.js',
      include: ['src/**/*.test.{js,jsx}'],
      // Siemens IX custom elements retain state across thread workers on
      // Windows. One forked worker isolates globals and exits deterministically
      // after the suite, trading a little speed for reliable CI completion.
      pool: 'forks',
      maxWorkers: 1,
      minWorkers: 1,
      teardownTimeout: 10_000,
    },
  };
});
