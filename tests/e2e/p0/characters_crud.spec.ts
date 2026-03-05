import { test, expect } from '@playwright/test';

test('create character and save', async ({ page }) => {

    await page.goto('http://localhost:3000');

    await page.getByTestId('activity-btn-characters').click();

    await page.getByTestId('new-character-btn').click();

    await page.getByTestId('character-name-input').fill('Test Character');

    await page.getByTestId('character-background-input').fill('Background story');

    await page.getByTestId('inspector-save').click();

    await expect(page.getByText('Saved')).toBeVisible();

});

test('candidate confirmation flow', async ({ page }) => {

    await page.goto('http://localhost:3000');

    await page.getByTestId('activity-btn-characters').click();

    // Find candidate card and confirm
    const candidateCard = page.getByTestId('candidate-card-cand_1');
    await expect(candidateCard).toBeVisible();
    
    await candidateCard.getByTestId('candidate-confirm-btn').click();

    // Candidate should disappear from candidate list
    await expect(candidateCard).not.toBeVisible();

    // Should appear in confirmed list
    await expect(page.getByTestId('character-list')).toContainText('Mysterious Stranger');
});