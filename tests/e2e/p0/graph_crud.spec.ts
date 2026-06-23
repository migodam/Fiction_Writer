import { test, expect } from '@playwright/test';

test.describe('Graph CRUD', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('http://localhost:3000');
        await page.getByTestId('activity-btn-graph').click();
        await expect(page.getByTestId('graph-board-flow')).toBeVisible();
    });

    test('graph node edit modal opens and saves', async ({ page }) => {
        const node = page.locator('[data-testid^="graph-node-"]').first();
        await node.dblclick();

        await expect(page.getByTestId('graph-node-edit-modal')).toBeVisible();

        await page.getByTestId('graph-node-modal-save-btn').click();

        await expect(page.getByTestId('graph-node-edit-modal')).not.toBeVisible();
    });

    // UNRESOLVED ELECTRON/MANUAL GAP: right-click on React Flow graph nodes does not reliably
    // trigger onNodeContextMenu in headless Chromium. Selectors updated (global-context-menu,
    // context-menu-item-delete) but the menu does not appear without a headed/Electron run.
    // See communication/2026-06-08-w4-qa-comms-merge-report.md § Unresolved Electron Gaps.
    test.skip('graph node delete via context menu', async ({ page }) => {
        const node = page.locator('[data-testid^="graph-node-"]').first();
        const nodeTestId = await node.getAttribute('data-testid');

        await node.click({ button: 'right' });

        await expect(page.getByTestId('global-context-menu')).toBeVisible();

        await page.getByTestId('context-menu-item-delete').click();

        if (nodeTestId) {
            await expect(page.getByTestId(nodeTestId)).not.toBeVisible();
        }
    });

    // UNRESOLVED ELECTRON/MANUAL GAP: right-click on world container button does not open
    // the context menu in headless Chromium. Selectors updated (global-context-menu,
    // context-menu-item-rename) but the menu does not appear without a headed/Electron run.
    // See communication/2026-06-08-w4-qa-comms-merge-report.md § Unresolved Electron Gaps.
    test.skip('world container rename via context menu', async ({ page }) => {
        await page.getByTestId('activity-btn-world').click();
        await expect(page.getByTestId('world-container-list')).toBeVisible();

        const container = page.locator('[data-testid^="world-container-"]').first();
        await container.click({ button: 'right' });

        await expect(page.getByTestId('global-context-menu')).toBeVisible();

        await page.getByTestId('context-menu-item-rename').click();

        await expect(page.getByTestId('world-container-rename-input')).toBeVisible();

        await page.getByTestId('world-container-rename-input').fill('Renamed Container');
        await page.keyboard.press('Enter');

        await expect(page.getByTestId('world-container-rename-input')).not.toBeVisible();
    });
});
