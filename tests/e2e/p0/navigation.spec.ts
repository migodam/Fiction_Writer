import { test, expect } from '@playwright/test';

test('activity bar navigation works', async ({ page }) => {

    await page.goto('http://localhost:3000');

    await page.getByTestId('activity-btn-characters').click();

    await expect(page.getByTestId('sidebar-section-characters-list')).toBeVisible();

    await page.getByTestId('activity-btn-timeline').click();

    await expect(page.getByTestId('timeline-canvas')).toBeVisible();

    await page.getByTestId('activity-btn-writing').click();

    await expect(page.getByTestId('writing-editor')).toBeVisible();

});