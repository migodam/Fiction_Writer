import { test, expect } from '@playwright/test';

test.describe('AI writing modal UI flow', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('http://localhost:3000');
        await page.getByTestId('activity-btn-writing').click();

        const scene = page.locator('[data-testid^="scene-item-"]').first();
        await scene.click();
    });

    test('continue modal opens and closes', async ({ page }) => {
        await page.getByTestId('writing-ai-continue-btn').click();

        await expect(page.getByTestId('ai-writing-modal')).toBeVisible();

        await page.getByTestId('ai-writing-close-btn').click();

        await expect(page.getByTestId('ai-writing-modal')).not.toBeVisible();
    });

    test('polish modal opens', async ({ page }) => {
        await page.getByTestId('writing-ai-polish-btn').click();

        await expect(page.getByTestId('ai-writing-modal')).toBeVisible();
    });
});
