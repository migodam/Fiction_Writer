import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from '@playwright/test';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..');

export default defineConfig({
    testDir: './e2e',
    timeout: 30000,
    retries: 1,
    use: {
        baseURL: 'http://localhost:3000',
        headless: true,
        viewport: { width: 1920, height: 1080 },
        ignoreHTTPSErrors: true,
    },
    webServer: {
        command: 'npm run ui:dev',
        cwd: repoRoot,
        url: 'http://localhost:3000',
        reuseExistingServer: true,
        timeout: 120000,
    },
    reporter: [
        ['list'],
        ['html', { outputFolder: 'playwright-report' }]
    ],

    projects: [
        {
            name: 'chromium',
            use: { browserName: 'chromium' }
        }
    ],
});
