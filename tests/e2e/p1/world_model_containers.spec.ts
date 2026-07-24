import { expect, test } from '@playwright/test';

test.describe('World model containers', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000');
    await page.getByTestId('activity-btn-world').click();
    await expect(page.getByTestId('world-container-list')).toBeVisible();
  });

  test('can create a container and attach a world item', async ({ page }) => {
    await page.getByTestId('create-container-btn').click();
    await expect(page.getByTestId('world-container-list')).toContainText('New notebook');

    await page.getByTestId('add-world-item-btn').click();
    await expect(page.getByTestId('world-item-name-input')).toBeVisible();

    await page.getByTestId('world-item-name-input').fill('Ancient Relic');
    await page.getByTestId('world-item-description-input').fill('A relic from the first age.');
    await expect(page.getByTestId('world-item-list')).toContainText('Ancient Relic');
  });
});
