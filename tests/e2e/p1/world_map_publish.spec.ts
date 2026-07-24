import { expect, test } from '@playwright/test';

test.describe('World map and publish exports', () => {
  test('world map renders markers and publish creates markdown/html artifacts', async ({ page }) => {
    await page.goto('http://localhost:3000');

    await page.goto('http://localhost:3000/world/maps');
    await expect(page.getByTestId('world-map-image')).toBeVisible();
    await expect(page.getByTestId('world-map-marker')).toHaveCount(4);

    await page.getByTestId('world-map-marker').first().click();
    await expect(page).toHaveURL(/\/timeline\/timeline\?worldItem=/);

    await page.getByTestId('activity-btn-publish').click();
    await expect(page.getByTestId('publish-preview-panel')).toContainText('#');

    const exportHistory = page.getByTestId('publish-export-history');

    await page.getByTestId('publish-format-markdown').click();
    await page.getByTestId('publish-export-action').click();
    await expect(exportHistory.getByTestId('publish-export-history-item-markdown')).toContainText(/\.md/);

    await page.getByTestId('publish-format-html').click();
    await page.getByTestId('publish-export-action').click();
    await expect(exportHistory.getByTestId('publish-export-history-item-html')).toContainText(/\.html/);
    await expect(exportHistory.getByTestId(/publish-export-history-item-(markdown|html)/)).toHaveCount(2);
  });
});
