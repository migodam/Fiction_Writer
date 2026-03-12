import { expect, test } from '@playwright/test';

test.describe('Project initialization and persistence', () => {
  test('can create a starter project, save, and reopen it', async ({ page }) => {
    await page.goto('http://localhost:3000');

    await page.getByTestId('toolbar-new-project').click();
    await expect(page.getByTestId('project-dialog')).toBeVisible();
    await page.getByTestId('project-name-input').fill('Acceptance Starter');
    await page.getByTestId('project-template-select').selectOption('starter-demo');
    await page.getByTestId('project-dialog-submit').click();

    await expect(page.getByTestId('status-bar')).toContainText('Acceptance Starter');
    await page.getByTestId('activity-btn-characters').click();
    await expect(page.getByTestId('character-list')).toContainText('Aria Solis');

    await page.getByTestId('new-character-btn').click();
    await page.getByTestId('character-name-input').fill('Persistence Witness');
    await page.getByTestId('character-background-input').fill('Used to verify project save and reopen.');
    await page.getByTestId('inspector-save').click();
    await page.getByTestId('toolbar-save').click();
    await expect(page.getByTestId('status-bar')).toContainText(/Saved|已保存/);

    await page.reload();
    await expect(page.getByTestId('status-bar')).toContainText('Acceptance Starter');
    await expect(page.getByTestId('character-list')).toContainText('Persistence Witness');

    await page.getByTestId('toolbar-open-project').click();
    await expect(page.getByTestId('project-dialog')).toBeVisible();
    await page.getByTestId('project-dialog-submit').click();
    await expect(page.getByTestId('status-bar')).toContainText('Acceptance Starter');
    await expect(page.getByTestId('character-list')).toContainText('Persistence Witness');
  });
});
