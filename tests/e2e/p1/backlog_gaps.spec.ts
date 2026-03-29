import { test, expect } from '@playwright/test';

test.describe('Backlog story gaps', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('http://localhost:3000');
        await page.getByTestId('activity-btn-workbench').click();
    });

    test('story gaps tab shows refresh button', async ({ page }) => {
        await page.getByTestId('backlog-story-gaps-tab').click();

        await expect(page.getByTestId('backlog-refresh-btn')).toBeVisible();
    });

    test('refresh shows gaps or empty state', async ({ page }) => {
        await page.getByTestId('backlog-story-gaps-tab').click();
        await page.getByTestId('backlog-refresh-btn').click();

        const noGaps = page.getByTestId('backlog-no-gaps');
        const gapItems = page.locator('[data-testid^="backlog-gap-item-"]');

        await expect(noGaps.or(gapItems.first())).toBeVisible();
    });
});
