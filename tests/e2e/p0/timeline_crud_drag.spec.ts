import { test, expect } from '@playwright/test';

test('create timeline event', async ({ page }) => {

  await page.goto('http://localhost:3000');

  await page.getByTestId('activity-btn-timeline').click();

  await page.getByTestId('add-event-btn').click();

  await page.getByTestId('event-title-input').fill('Test Event');

  await page.getByTestId('event-summary-input').fill('Something happens');

  await page.getByTestId('inspector-save').click();

  await expect(page.getByText('Saved')).toBeVisible();

});