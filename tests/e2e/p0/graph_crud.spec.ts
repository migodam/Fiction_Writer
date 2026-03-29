import { test, expect } from '@playwright/test';

test.describe('Graph CRUD', () => {
    test.beforeEach(async ({ page }) => {
        await page.goto('http://localhost:3000');
        await page.getByTestId('activity-btn-graph').click();
        await expect(page.getByTestId('graph-canvas')).toBeVisible();
    });

    test('graph node edit modal opens and saves', async ({ page }) => {
        const node = page.locator('[data-testid^="graph-node-"]').first();
        await node.dblclick();

        await expect(page.getByTestId('graph-node-edit-modal')).toBeVisible();

        await page.getByTestId('graph-node-modal-save-btn').click();

        await expect(page.getByTestId('graph-node-edit-modal')).not.toBeVisible();
    });

    test('graph node delete via context menu', async ({ page }) => {
        const node = page.locator('[data-testid^="graph-node-"]').first();
        const nodeTestId = await node.getAttribute('data-testid');

        await node.click({ button: 'right' });

        await expect(page.getByTestId('graph-context-menu')).toBeVisible();

        await page.getByTestId('graph-context-delete-btn').click();

        if (nodeTestId) {
            await expect(page.getByTestId(nodeTestId)).not.toBeVisible();
        }
    });

    test('world container rename via context menu', async ({ page }) => {
        await page.getByTestId('activity-btn-world').click();
        await expect(page.getByTestId('world-container-list')).toBeVisible();

        const container = page.locator('[data-testid^="world-container-"]').first();
        await container.click({ button: 'right' });

        await expect(page.getByTestId('world-context-menu')).toBeVisible();

        await page.getByTestId('world-context-rename-btn').click();

        await expect(page.getByTestId('world-container-rename-input')).toBeVisible();

        await page.getByTestId('world-container-rename-input').fill('Renamed Container');
        await page.keyboard.press('Enter');

        await expect(page.getByTestId('world-container-rename-input')).not.toBeVisible();
    });
});
