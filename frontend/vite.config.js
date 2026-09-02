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
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: './src/setupTests.js',
      include: ['src/**/*.test.{js,jsx}'],
    },
  };
});
