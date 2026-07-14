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

    test('graph node delete via context menu', async ({ page }) => {
        const node = page.locator('[data-testid^="graph-node-"]').first();
        const nodeTestId = await node.getAttribute('data-testid');

        await node.click({ button: 'right' });

        await expect(page.getByTestId('global-context-menu')).toBeVisible();

        const deleteCommand = page.getByTestId('context-menu-item-delete');
        await deleteCommand.click();
        await expect(deleteCommand).toContainText('Confirm');
        if (nodeTestId) {
            await expect(page.getByTestId(nodeTestId)).toBeVisible();
        }

        await deleteCommand.click();
        await expect(page.getByTestId('global-context-menu')).not.toBeVisible();

        if (nodeTestId) {
            await expect(page.getByTestId(nodeTestId)).not.toBeVisible();
        }
    });

    test('world container rename via context menu', async ({ page }) => {
        await page.getByTestId('activity-btn-world').click();
        await expect(page.getByTestId('world-container-list')).toBeVisible();

        const container = page.locator('[data-testid^="world-container-"]').first();
        await container.click({ button: 'right' });

        await expect(page.getByTestId('global-context-menu')).toBeVisible();

        await page.getByTestId('context-menu-item-world-folder-rename').click();

        await expect(page.getByTestId('world-container-rename-input')).toBeVisible();

        await page.getByTestId('world-container-rename-input').fill('Renamed Container');
        await page.keyboard.press('Enter');

        await expect(page.getByTestId('world-container-rename-input')).not.toBeVisible();
        await expect(page.getByTestId('world-container-list')).toContainText('Renamed Container');
    });

    test('graph node updates stay inside a pending undo transaction', async ({ page }) => {
        await page.evaluate(() => {
            const store = (window as any).__narrativeStore;
            store.setState({ undoStack: [], redoStack: [] });
            const state = store.getState();
            const board = state.graphBoards[0];
            const node = board.nodes[0];
            store.getState().beginUndoTransaction('Move graph node');
            store.getState().updateGraphNode(board.id, { ...node, x: node.x + 80, y: node.y + 40 });
        });

        await expect.poll(() => page.evaluate(() => {
            const state = (window as any).__narrativeStore.getState();
            return { undoDepth: state.undoStack.length, pending: Boolean(state.pendingUndoTransaction) };
        })).toEqual({ undoDepth: 0, pending: true });

        await page.evaluate(() => (window as any).__narrativeStore.getState().commitUndoTransaction());
        await expect.poll(() => page.evaluate(() => (window as any).__narrativeStore.getState().undoStack.length)).toBe(1);
    });

    test('one real graph drag creates one undo entry and one undo restores its position', async ({ page }) => {
        await page.evaluate(() => {
            const store = (window as any).__narrativeStore;
            store.setState({
                graphBoards: [{
                    id: 'drag_board', name: 'Drag Board', description: '', sortOrder: 0, selectedNodeIds: [], edges: [],
                    view: { zoom: 1, panX: 0, panY: 0 },
                    nodes: [{ id: 'drag_node', kind: 'free_note', label: 'Drag me', description: '', x: 180, y: 180, width: 180, height: 80, linkedEntityId: null, linkedEntityType: null }],
                }],
                activeGraphBoardId: 'drag_board',
                undoStack: [],
                redoStack: [],
                pendingUndoTransaction: null,
            });
        });

        const node = page.getByTestId('graph-node-drag_node');
        await expect(node).toBeVisible();
        const box = await node.boundingBox();
        expect(box).not.toBeNull();
        if (!box) throw new Error('Graph node did not have a bounding box');

        await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
        await page.mouse.down();
        await page.mouse.move(box.x + box.width / 2 + 140, box.y + box.height / 2 + 80, { steps: 8 });
        await page.mouse.up();

        await expect.poll(() => page.evaluate(() => {
            const state = (window as any).__narrativeStore.getState();
            const node = state.graphBoards.find((board: any) => board.id === 'drag_board').nodes[0];
            return { moved: node.x > 180 && node.y > 180, undoDepth: state.undoStack.length, pending: state.pendingUndoTransaction };
        })).toEqual({ moved: true, undoDepth: 1, pending: null });

        await page.evaluate(async () => { await (window as any).__narrativeStore.getState().undoAction(); });
        await expect.poll(() => page.evaluate(() => {
            const state = (window as any).__narrativeStore.getState();
            const node = state.graphBoards.find((board: any) => board.id === 'drag_board').nodes[0];
            return { x: node.x, y: node.y, undoDepth: state.undoStack.length };
        })).toEqual({ x: 180, y: 180, undoDepth: 0 });
    });
});
