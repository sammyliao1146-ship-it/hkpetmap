import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({mode}) => {
  const devEnv = loadEnv(mode, '.', 'PET_');
  return {
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id) => (id.includes('node_modules/maplibre-gl') ? 'maplibre' : undefined),
      },
    },
  },
  server: {
    port: 5174,
    strictPort: true,
    proxy: { '/api': devEnv.PET_API_PROXY_TARGET || 'http://127.0.0.1:8001' },
  },
  };
});
