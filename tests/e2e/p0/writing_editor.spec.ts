import { test, expect } from '@playwright/test';

test('writing editor typing and autosave', async ({ page }) => {

  await page.goto('http://localhost:3000');

  await page.getByTestId('activity-btn-writing').click();

  const editor = page.getByTestId('writing-editor');

  await editor.click();

  await page.keyboard.type('Hello world');

  await expect(page.getByText('Saved', { exact: true })).toBeVisible();

});