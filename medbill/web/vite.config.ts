import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'

// The dev server proxies /api so the browser sees one origin. A port override keeps demos isolated.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    port: Number(process.env.MEDBILL_WEB_PORT ?? process.env.WEB_PORT ?? 5173),
    proxy: { '/api': { target: `http://127.0.0.1:${Number(process.env.MEDBILL_API_PORT ?? process.env.API_PORT ?? 8000)}`, rewrite: (p) => p.replace(/^\/api/, '') } },
  },
})
