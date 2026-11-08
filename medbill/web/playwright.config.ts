import { defineConfig, devices } from '@playwright/test'

// Starts the API in DEMO_MODE (no network, no model) and the Vite dev server.
// Set PY to the Python that has the backend dependencies installed (default: python3).
const py = process.env.PY ?? 'python3'
const apiPort = Number(process.env.MEDBILL_API_PORT ?? process.env.API_PORT ?? 18181)
const webPort = Number(process.env.MEDBILL_WEB_PORT ?? process.env.WEB_PORT ?? 15174)
if (![apiPort, webPort].every((port) => Number.isInteger(port) && port > 0 && port < 65536) || apiPort === webPort) {
  throw new Error('Choose distinct, valid API and web ports.')
}
const baseURL = process.env.BASE_URL ?? `http://127.0.0.1:${webPort}`

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: 0,
  reporter: [['list']],
  use: { baseURL, trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'phone-375', use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 800 } } },
  ],
  webServer: [
    {
      command: `"${py}" -m uvicorn api.main:app_factory --factory --host 127.0.0.1 --port ${apiPort}`,
      cwd: '..',
      url: `http://127.0.0.1:${apiPort}/health`,
      env: { DEMO_MODE: '1' },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    { command: `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${webPort} --strictPort`, url: baseURL,
      env: { MEDBILL_API_PORT: String(apiPort) }, reuseExistingServer: false, timeout: 60_000 },
  ],
})
