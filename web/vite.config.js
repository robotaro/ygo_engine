import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// The Svelte dev server proxies the WebSocket to the FastAPI backend on :8000.
export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: {
      '/ws': { target: 'ws://localhost:8000', ws: true },
      '/api': 'http://localhost:8000',
    },
  },
})
