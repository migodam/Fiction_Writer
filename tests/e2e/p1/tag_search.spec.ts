import { test, expect } from '@playwright/test';

test.describe('Tag character search', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('http://localhost:3000');
        await page.getByTestId('activity-btn-characters').click();
    });

    test('search filter input is visible after selecting a tag', async ({ page }) => {
        await page.getByTestId('sidebar-section-characters-tags').click();

        const tag = page.locator('[data-testid^="character-tag-"]').first();
        await tag.click();

        await expect(page.getByTestId('tag-character-search-input')).toBeVisible();

        await page.getByTestId('tag-character-search-input').fill('hero');
    });
});
