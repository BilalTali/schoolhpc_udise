import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: {
      // only this computer by default; VITE_HOST=0.0.0.0 opens it to the network (plain http - trusted networks only)
      host: env.VITE_HOST || '127.0.0.1',
      port: 5173,
      // The web app calls /api on its own address, so the login cookie is same-origin.
      // xfwd passes the browser's address on, so the login limit counts per browser, not per dev server
      proxy: { '/api': { target: env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000', changeOrigin: false, xfwd: true } },
    },
  }
})
