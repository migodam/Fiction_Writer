import { test, expect } from '@playwright/test';

test.describe('Narrative IDE Smoke Test', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000');
  });

  test('app layout is visible', async ({ page }) => {
    await expect(page.getByTestId('top-toolbar')).toBeVisible();
    await expect(page.getByTestId('activity-bar')).toBeVisible();
    await expect(page.getByTestId('sidebar')).toBeVisible();
    await expect(page.getByTestId('workspace')).toBeVisible();
    await expect(page.getByTestId('inspector')).toBeVisible();
    await expect(page.getByTestId('status-bar')).toBeVisible();
  });

  test('can navigate through activities', async ({ page }) => {
    await page.getByTestId('activity-btn-characters').click();
    await expect(page.getByTestId('character-list')).toBeVisible();
    
    await page.getByTestId('activity-btn-timeline').click();
    await expect(page.getByTestId('timeline-canvas')).toBeVisible();
  });

  test('command palette opens and navigates', async ({ page }) => {
    // Open Command Palette via search button (more stable in tests than shortcuts)
    await page.getByTestId('toggle-command-palette').click();
    await expect(page.getByTestId('command-palette')).toBeVisible();
    
    // Type and click an option
    await page.keyboard.type('Writing');
    await page.getByText('Go to Writing Studio').click();
    
    // Assert navigation
    await expect(page.getByTestId('writing-editor')).toBeVisible();
    await expect(page.getByTestId('command-palette')).not.toBeVisible();
  });
});
