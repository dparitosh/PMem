import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  // The application was migrated from CRA.  Vite exposes only VITE_* values
  // by default, while the existing customer deployment files use REACT_APP_*.
  // Load both prefixes explicitly and compile only browser-safe UI settings.
  const loaded = loadEnv(mode, process.cwd(), '');
  const clientEnv = Object.fromEntries(
    Object.entries({ ...loaded, ...process.env }).filter(([key]) =>
      key.startsWith('VITE_') || key.startsWith('REACT_APP_') || key === 'HOST'
    ),
  );

  return {
    plugins: [react()],
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
      // The graph and Siemens IX suites are memory-heavy. Keep a small pool
      // of isolated workers: a single worker leaks IX custom-element state
      // across files, while an unrestricted pool exhausts the Node heap.
      pool: 'threads',
      maxWorkers: 2,
      minWorkers: 1,
    },
  };
});
