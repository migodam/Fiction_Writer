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