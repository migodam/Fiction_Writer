import { expect, test } from '@playwright/test';

test.describe('World map and publish exports', () => {
  test('world map renders markers and publish creates markdown/html artifacts', async ({ page }) => {
    await page.goto('http://localhost:3000');

    await page.goto('http://localhost:3000/world/maps');
    await expect(page.getByTestId('world-map-image')).toBeVisible();
    await expect(page.getByTestId('world-map-marker')).toHaveCount(4);

    await page.getByTestId('world-map-marker').first().click();
    await expect(page).toHaveURL(/\/timeline\/events\?location=/);

    await page.getByTestId('activity-btn-publish').click();
    await expect(page.getByTestId('publish-preview-panel')).toContainText('#');

    await page.getByTestId('publish-export-markdown').click();
    await page.getByTestId('publish-export-html').click();
    await expect(page.getByTestId('publish-export-history')).toContainText('.md');
    await expect(page.getByTestId('publish-export-history')).toContainText('.html');
  });
});
