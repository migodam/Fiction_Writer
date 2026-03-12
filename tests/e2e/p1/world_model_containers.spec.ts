import { expect, test } from '@playwright/test';

test.describe('World model containers', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000');
    await page.getByTestId('activity-btn-world').click();
    await expect(page.getByTestId('world-container-list')).toBeVisible();
  });

  test('can create a container and attach a world item', async ({ page }) => {
    await page.getByTestId('create-container-btn').click();
    await expect(page.getByTestId('world-container-list')).toContainText('New Container');

    await page.getByTestId('add-world-item-btn').click();
    await expect(page.getByTestId('world-item-name-input')).toBeVisible();

    await page.getByTestId('world-item-name-input').fill('Ancient Relic');
    await page.getByTestId('world-item-description-input').fill('A relic from the first age.');
    await page.getByTestId('dynamic-field-add-row').click();
    await page.getByTestId('dynamic-field-key-input').fill('Power Level');
    await page.getByTestId('dynamic-field-value-input').fill('Over 9000');
    await page.getByTestId('inspector-save').click();

    await expect(page.getByText('Saved', { exact: true })).toBeVisible();
    await expect(page.getByTestId('world-item-list')).toContainText('Ancient Relic');
  });
});
