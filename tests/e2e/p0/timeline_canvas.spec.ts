import { test, expect } from '@playwright/test';

test.describe('Timeline canvas', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('http://localhost:3000');
        await page.getByTestId('activity-btn-timeline').click();
    });

    test('canvas renders', async ({ page }) => {
        await expect(page.getByTestId('timeline-canvas')).toBeVisible();
    });

    test('event edit drawer opens, accepts input, and closes on save', async ({ page }) => {
        await expect(page.getByTestId('timeline-canvas')).toBeVisible();

        const eventNode = page.locator('[data-testid^="timeline-event-node-"]').first();
        await eventNode.dblclick();

        await expect(page.getByTestId('event-edit-drawer')).toBeVisible();

        await page.getByTestId('event-edit-title').fill('Updated Event Title');

        await page.getByTestId('event-edit-save-btn').click();

        await expect(page.getByTestId('event-edit-drawer')).not.toBeVisible();
    });
});
