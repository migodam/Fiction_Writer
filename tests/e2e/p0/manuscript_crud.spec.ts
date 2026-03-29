import { test, expect } from '@playwright/test';

test.describe('Manuscript workspace', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('http://localhost:3000');
        await page.getByTestId('activity-btn-writing').click();
    });

    test('manuscript workspace renders', async ({ page }) => {
        await expect(page.getByTestId('manuscript-workspace')).toBeVisible();
    });

    test('add node creates entry in manuscript tree', async ({ page }) => {
        await expect(page.getByTestId('manuscript-workspace')).toBeVisible();

        await page.getByTestId('manuscript-add-node-btn').click();

        await page.getByTestId('manuscript-node-title-input').fill('New Chapter Node');
        await page.getByTestId('manuscript-node-confirm-btn').click();

        await expect(page.getByTestId('manuscript-workspace')).toContainText('New Chapter Node');
    });
});
