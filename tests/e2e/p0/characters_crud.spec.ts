import { test, expect } from '@playwright/test';

test('create character and save', async ({ page }) => {

    await page.goto('/');

    await page.getByTestId('activity-btn-characters').click();

    await page.getByTestId('new-character-btn').click();

    await page.getByTestId('character-name-input').fill('Test Character');

    await page.getByTestId('character-background-input').fill('Background story');

    await page.getByTestId('inspector-save').click();

    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

});

test('candidate confirmation flow', async ({ page }) => {

    await page.goto('/');

    await page.getByTestId('activity-btn-characters').click();
    await page.getByTestId('sidebar-section-characters-candidates').click();

    const candidateCard = page.getByTestId('candidate-card-cand_1');
    await expect(candidateCard).toBeVisible();
    
    await candidateCard.getByTestId('candidate-confirm-btn').click();

    await expect(page).toHaveURL(/\/characters\/profile\/cand_1$/);
    await expect(page.getByTestId('character-list')).toContainText('Mysterious Stranger');
    await expect(page.getByTestId('character-name-input')).toHaveValue('Mysterious Stranger');
});
