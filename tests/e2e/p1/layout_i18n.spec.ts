import { expect, test } from '@playwright/test';

test.describe('Layout and language settings', () => {
  test('can switch languages, collapse sidebar, and resize panels', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const modal = page.getByTestId('settings-modal');
    await page.getByTestId('toolbar-settings').click();
    await expect(modal).toBeVisible();
    await page.getByTestId('locale-zh').click();
    await expect(page.getByText('工作台').first()).toBeVisible();
    await page.getByTestId('locale-en').click();
    await expect(page.getByText('Workbench').first()).toBeVisible();
    await modal.locator('button').first().click();
    await expect(modal).not.toBeVisible();

    const sidebarHandle = await page.getByTestId('sidebar-resizer').boundingBox();
    if (!sidebarHandle) throw new Error('Missing sidebar resizer');
    const initialSidebarX = sidebarHandle.x;
    await page.mouse.move(sidebarHandle.x + 1, sidebarHandle.y + 4);
    await page.mouse.down();
    await page.mouse.move(sidebarHandle.x + 90, sidebarHandle.y + 4);
    await page.mouse.up();
    await expect.poll(async () => (await page.getByTestId('sidebar-resizer').boundingBox())?.x ?? 0).toBeGreaterThan(initialSidebarX + 40);

    const inspectorHandle = await page.getByTestId('inspector-resizer').boundingBox();
    if (!inspectorHandle) throw new Error('Missing inspector resizer');
    const initialInspectorX = inspectorHandle.x;
    await page.mouse.move(inspectorHandle.x + 1, inspectorHandle.y + 4);
    await page.mouse.down();
    await page.mouse.move(inspectorHandle.x - 90, inspectorHandle.y + 4);
    await page.mouse.up();
    await expect.poll(async () => (await page.getByTestId('inspector-resizer').boundingBox())?.x ?? 0).toBeLessThan(initialInspectorX - 40);

    const dockHandle = await page.getByTestId('agentDock-resizer').boundingBox();
    if (!dockHandle) throw new Error('Missing dock resizer');
    const initialDockX = dockHandle.x;
    await page.mouse.move(dockHandle.x + 1, dockHandle.y + 4);
    await page.mouse.down();
    await page.mouse.move(dockHandle.x - 90, dockHandle.y + 4);
    await page.mouse.up();
    await expect.poll(async () => (await page.getByTestId('agentDock-resizer').boundingBox())?.x ?? 0).toBeLessThan(initialDockX - 40);

    await page.getByTestId('toolbar-toggle-sidebar').click();
    await expect(page.getByTestId('sidebar-resizer')).not.toBeVisible();

    await page.getByTestId('toolbar-toggle-sidebar').click();
    await expect(page.getByTestId('sidebar-resizer')).toBeVisible();

    await page.getByTestId('ai-assistant').click();
    await expect(page.getByTestId('agent-dock-collapsed')).toBeVisible();
    await page.getByTestId('agent-dock-expand').click();
    await expect(page.getByTestId('agent-dock')).toBeVisible();
  });
});
