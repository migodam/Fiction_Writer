import { expect, test } from '@playwright/test';

test.describe('Graph and Workbench flow', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000');
  });

  test('graph can queue a sync proposal into workbench', async ({ page }) => {
    await page.getByTestId('activity-btn-graph').click();
    await expect(page.getByTestId('graph-canvas')).toBeVisible();

    await page.getByTestId('graph-node-char_aria').click();
    await page.getByTestId('graph-sync-selection-btn').click();
    await expect(page.getByText('Proposal queued', { exact: true })).toBeVisible();

    await page.getByTestId('activity-btn-workbench').click();
    await expect(page.getByTestId('workbench-inbox-list')).toBeVisible();
    await expect(page.getByText('Graph sync batch')).toBeVisible();
  });

  test('agent dock can be collapsed and restored without losing workbench context', async ({ page }) => {
    await expect(page.getByTestId('agent-dock')).toBeVisible();

    await page.getByTestId('ai-assistant').click();
    await expect(page.getByTestId('agent-dock-collapsed')).toBeVisible();

    await page.getByTestId('agent-dock-expand').click();
    await expect(page.getByTestId('agent-dock')).toBeVisible();

    await page.getByTestId('activity-btn-workbench').click();
    await expect(page.getByTestId('workbench-inbox-list')).toBeVisible();
  });
});
