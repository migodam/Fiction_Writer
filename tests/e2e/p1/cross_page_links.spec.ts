import { expect, test } from '@playwright/test';

test.describe('Cross-page links', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000');
  });

  test('character profile actions deep-link into timeline and graph', async ({ page }) => {
    await page.getByTestId('activity-btn-characters').click();
    await page.getByTestId('new-character-btn').click();
    await page.getByTestId('character-name-input').fill('Deep Link Hero');
    await page.getByTestId('character-background-input').fill('Created to verify route handoffs.');
    await page.getByTestId('inspector-save').click();
    await expect(page.getByText(/Saved|已保存/)).toBeVisible();

    await page.getByTestId('open-character-timeline-btn').click();
    await expect(page).toHaveURL(/\/timeline\/events\?character=/);
    await expect(page.getByTestId('timeline-canvas')).toBeVisible();
    await expect(page.getByTestId('timeline-filter-state')).toContainText('Deep Link Hero');

    await page.getByTestId('activity-btn-characters').click();
    await page.getByText('Deep Link Hero').first().click();
    await page.getByTestId('open-character-relationships-btn').click();
    await expect(page).toHaveURL(/\/graph\/relationships$/);
    await expect(page.getByTestId('graph-canvas')).toBeVisible();
  });

  test('world location and timeline events can deep-link into filtered timeline and writing', async ({ page }) => {
    await page.getByTestId('activity-btn-world').click();
    await page.getByTestId('world-container-cont_locations').click();
    await page.getByTestId('world-item-loc_glass_bridge').click();
    await page.getByTestId('open-world-timeline-btn').click();

    await expect(page).toHaveURL(/\/timeline\/events\?location=loc_glass_bridge/);
    await expect(page.getByTestId('timeline-filter-state')).toContainText('Glass Bridge');

    await page.getByTestId('timeline-node-event_bridge').first().click();
    await page.getByTestId('timeline-open-scene-btn').first().click();
    await expect(page.getByTestId('writing-editor')).toBeVisible();
    await expect(page.locator('input[value="Glass Bridge Intercept"]')).toBeVisible();
  });

  test('workbench proposal actions move items into history without unread revisit', async ({ page }) => {
    await page.getByTestId('activity-btn-workbench').click();
    await expect(page.getByText('Convert public fallout note into timeline candidate')).toBeVisible();

    await page.getByTestId('proposal-accept-btn').first().click();
    await page.getByTestId('sidebar-section-workbench-history').click();

    const historyList = page.getByTestId('workbench-history-list');
    await expect(historyList).toContainText('Convert public fallout note into timeline candidate');
    await expect(historyList.getByText('accepted').first()).toBeVisible();
  });
});
