import { test, expect } from '@playwright/test';

test.describe('characters route contract', () => {
  test('candidate queue is reachable by route and section selector', async ({ page }) => {
    await page.goto('/characters/candidates');

    await expect(page.getByTestId('sidebar-section-characters-candidates')).toBeVisible();
    await expect(page.getByTestId('candidate-card-cand_1')).toBeVisible();
  });

  test('character profile route loads the selected record', async ({ page }) => {
    await page.goto('/characters/profile/char_1');

    await expect(page.getByTestId('character-name-input')).toHaveValue('Silas Vane');
    await expect(page.getByTestId('character-background-input')).toContainText('rogue scholar');
    await expect(page.getByTestId('status-bar')).toContainText('Silas Vane');
  });

  test('invalid character profile shows not-found state and recovery action', async ({ page }) => {
    await page.goto('/characters/profile/missing-character');

    await expect(page.getByTestId('entity-not-found')).toContainText('Entity not found');
    await page.getByTestId('entity-not-found-back').click();
    await expect(page).toHaveURL(/\/characters\/list$/);
    await expect(page.getByTestId('character-list')).toBeVisible();
  });
});
