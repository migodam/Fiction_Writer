import { defineConfig } from '@playwright/test';

export default defineConfig({
    testDir: './e2e',

    timeout: 30000,

    retries: 1,

    use: {
        headless: true,
        viewport: { width: 1920, height: 1080 },
        ignoreHTTPSErrors: true,
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