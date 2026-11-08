import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

// The API runs on :8000 (override with API_PORT); the dev server proxies /api to it so the browser sees one origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    port: Number(process.env.WEB_PORT ?? 5173),
    proxy: { '/api': { target: `http://127.0.0.1:${process.env.API_PORT ?? 8000}`, rewrite: (p) => p.replace(/^\/api/, '') } },
  },
})
