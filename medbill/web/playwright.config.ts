import { defineConfig, devices } from '@playwright/test'

// Starts the API in DEMO_MODE (no network, no model) and the Vite dev server.
// Set PY to the Python that has the backend dependencies installed (default: python3).
const py = process.env.PY ?? 'python3'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  retries: 0,
  reporter: [['list']],
  use: { baseURL: process.env.BASE_URL ?? 'http://127.0.0.1:5173', trace: 'retain-on-failure' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'phone-375', use: { ...devices['Desktop Chrome'], viewport: { width: 375, height: 800 } } },
  ],
  webServer: [
    {
      command: `"${py}" -m uvicorn api.main:app_factory --factory --port 8000`,
      cwd: '..',
      url: 'http://127.0.0.1:8000/health',
      env: { DEMO_MODE: '1' },
      reuseExistingServer: true,
      timeout: 60_000,
    },
    { command: 'npm run dev -- --host 127.0.0.1', url: 'http://127.0.0.1:5173', reuseExistingServer: true, timeout: 60_000 },
  ],
})
