import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

const frontendRoot = fileURLToPath(new URL('.', import.meta.url))

// https://vitejs.dev/config/
export default defineConfig({
  root: frontendRoot,
  plugins: [react()],
  server: {
    host: true,
    port: Number(process.env.VITE_PORT || 5173),
    strictPort: true,
    proxy: {
      '/api': {
        // A staging/QA session runs its own backend on another port; the app
        // itself never changes.
        target: process.env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
