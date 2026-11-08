import { defineConfig, devices } from '@playwright/test';
import path from 'node:path';

// The pages in a real browser, with the API's answers from tests/api.ts (typed with the frontend's own types): no
// backend, family hub or database. The backend's behaviour is tested by pytest (tests/)
export const FRONTEND = 'http://localhost:3120';

export default defineConfig({
    testDir: './tests',
    fullyParallel: true,
    retries: process.env.CI ? 1 : 0,
    reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
    use: {
        baseURL: FRONTEND,
        locale: 'de-CH',
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
    },
    projects: [
        { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1180, height: 820 } } },
        { name: 'phone', use: { ...devices['Pixel 7'] } },
    ],
    webServer: {
        // An API proxy to nowhere: every /api request is answered by the test, one it doesn't know fails
        command: 'npx vite --port 3120 --strictPort',
        cwd: path.resolve(__dirname, '..', 'frontend'),
        url: FRONTEND,
        env: { API_PROXY: 'http://127.0.0.1:9' },
        reuseExistingServer: false,
        timeout: 60_000,
    },
});
