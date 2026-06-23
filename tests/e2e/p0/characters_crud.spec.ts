import { test, expect } from '@playwright/test';

test('create character and save', async ({ page }) => {
  await page.goto('/');

  await page.getByTestId('activity-btn-characters').click();
  await page.getByTestId('new-character-btn').click();
  await page.getByTestId('character-name-input').fill('Test Character');
  await page.getByTestId('character-background-input').fill('Background story');
  await page.getByTestId('inspector-save').click();

  await expect(page.getByText(/Saved|已保存/)).toBeVisible();
});

test('profile tab exposes all documented fields', async ({ page }) => {
  await page.goto('/characters/profile/char_aria');

  await expect(page.getByTestId('character-name-input')).toBeVisible();
  await expect(page.getByTestId('character-background-input')).toBeVisible();
  await expect(page.getByTestId('character-summary-input')).toBeVisible();
  await expect(page.getByTestId('character-traits-input')).toBeVisible();
  await expect(page.getByTestId('character-goals-input')).toBeVisible();
  await expect(page.getByTestId('character-fears-input')).toBeVisible();
  await expect(page.getByTestId('character-birthday-input')).toBeVisible();
  await expect(page.getByTestId('character-speechstyle-input')).toBeVisible();
  await expect(page.getByTestId('character-arc-input')).toBeVisible();

  await page.getByTestId('character-traits-input').fill('坚韧, 谨慎');
  await page.getByTestId('inspector-save').click();
  await expect(page.getByText(/Saved|已保存/)).toBeVisible();
  await expect(page.getByTestId('character-traits-input')).toHaveValue('坚韧, 谨慎');
});

test('candidate confirmation flow', async ({ page }) => {
  await page.goto('/');

  await page.getByTestId('activity-btn-characters').click();
  await page.getByTestId('sidebar-section-characters-candidates').click();

  const candidateCard = page.getByTestId('candidate-card-cand_mina');
  await expect(candidateCard).toBeVisible();
  await expect(candidateCard).toContainText('Mina Vale');

  await candidateCard.getByTestId('candidate-confirm-btn').click();

  await expect(page).toHaveURL(/\/characters\/profile\/cand_mina$/);
  await expect(page.getByTestId('character-list')).toContainText('Mina Vale');
  await expect(page.getByTestId('character-name-input')).toHaveValue('Mina Vale');
});
