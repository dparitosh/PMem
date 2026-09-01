import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // The application configuration is shared with the prior CRA build and
  // reads REACT_APP_* variables from process.env. Map that access to Vite's
  // browser-safe environment object so the client does not crash at startup.
  define: {
    'process.env': 'import.meta.env',
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
});
