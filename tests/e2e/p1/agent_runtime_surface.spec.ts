import { expect, test } from '@playwright/test';

test('Agent Dock opens the same durable execution surface as the full Agents workspace', async ({ page }) => {
  await page.goto('http://localhost:3000');

  const dock = page.getByTestId('agent-dock');
  if (!(await dock.isVisible())) {
    await page.getByTestId('agent-dock-expand').click();
  }

  await expect(page.getByTestId('agent-runtime-surface')).toBeVisible();
  await expect(page.getByTestId('agent-runtime-summary')).toBeVisible();
  await expect(page.getByTestId('agent-runtime-agent-all')).toBeVisible();
  await expect(page.getByTestId('agent-runtime-no-hidden-thought')).toContainText('Private reasoning is not displayed');
  await expect(page.getByTestId('agent-runtime-empty')).toBeVisible();

  await page.getByTestId('agent-runtime-open-workspace').click();
  await expect(page).toHaveURL(/\/agents/);
  await expect(page.getByTestId('agent-workspace')).toBeVisible();
  await expect(page.getByTestId('agent-runs-panel').getByTestId('agent-runtime-surface')).toBeVisible();
  await expect(page.getByTestId('agent-runs-panel').getByTestId('agent-runtime-empty')).toBeVisible();
});
