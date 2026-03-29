import { test, expect } from '@playwright/test';

test.describe('Chapter preview modal', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('http://localhost:3000');
        await page.getByTestId('activity-btn-writing').click();
    });

    test('chapter preview modal opens and closes', async ({ page }) => {
        const previewBtn = page.locator('[data-testid^="chapter-preview-btn-"]').first();
        await previewBtn.click();

        await expect(page.getByTestId('chapter-preview-modal')).toBeVisible();
        await expect(page.getByTestId('chapter-preview-stats')).toBeVisible();

        await page.getByTestId('chapter-preview-close-btn').click();

        await expect(page.getByTestId('chapter-preview-modal')).not.toBeVisible();
    });
});
