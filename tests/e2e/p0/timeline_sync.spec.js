import { test, expect } from '@playwright/test';

// ── Helpers ──────────────────────────────────────────────────────────────────

async function openTimelineWorkspace(page) {
  await page.goto('/');
  await page.getByTestId('activity-btn-timeline').click();
  await expect(page.getByTestId('timeline-canvas')).toBeVisible();
}

async function openBranchContextMenu(page, hitArea) {
  await hitArea.dispatchEvent('contextmenu', {
    bubbles: true,
    cancelable: true,
    clientX: 120,
    clientY: 120,
  });
  await expect(page.getByTestId('timeline-branch-context-menu')).toBeVisible();
}

async function addEmptyBranch(page) {
  await page.evaluate(() => {
    const id = 'timeline_delete_test_branch';
    window.__narrativeStore.setState((state) => ({
      timelineBranches: [
        ...state.timelineBranches.filter((branch) => branch.id !== id),
        {
          id,
          name: 'Delete Test Branch',
          description: '',
          parentBranchId: null,
          forkEventId: null,
          mergeEventId: null,
          color: '#38bdf8',
          sortOrder: 999,
          collapsed: false,
          mode: 'independent',
          startAnchor: null,
          endAnchor: null,
          endMode: 'open',
          mergeTargetBranchId: null,
          geometry: { laneOffset: 270, bend: 0.25, thickness: 1 },
        },
      ],
    }));
  });
  return page.getByTestId('timeline-branch-hitarea-timeline_delete_test_branch');
}

// ── Sync bug: orphan cleanup ──────────────────────────────────────────────────

test.describe('Timeline sync — orphan file cleanup', () => {
  test('deleting a timeline event removes it from the canonical save payload', async ({ page }) => {
    await openTimelineWorkspace(page);

    // Wait for at least one event node to be rendered.
    const firstNode = page.locator('[data-testid^="timeline-event-node-"]').first();
    await expect(firstNode).toBeVisible();
    const eventId = (await firstNode.getAttribute('data-testid')).replace('timeline-event-node-', '');

    // Click the node to open the edit modal.
    await firstNode.click();
    await expect(page.getByTestId('event-edit-modal')).toBeVisible();

    // Delete the event.
    await page.getByTestId('event-edit-delete-btn').click();
    await expect(page.getByTestId('event-edit-modal')).not.toBeVisible();

    await page.waitForFunction(() =>
      window.__narrativeStore.getState().saveStatus !== 'Unsaved changes',
    );
    expect(await page.evaluate((id) =>
      window.__narrativeStore.getState().timelineEvents.some((event) => event.id === id),
      eventId,
    )).toBe(false);
  });

  test('canonical event count matches rendered nodes after deletion', async ({ page }) => {
    await openTimelineWorkspace(page);

    const nodes = page.locator('[data-testid^="timeline-event-node-"]');
    const initialCount = await nodes.count();
    if (initialCount < 2) test.skip(); // need at least 2 events

    // Delete the first event.
    await nodes.first().click();
    await expect(page.getByTestId('event-edit-modal')).toBeVisible();
    await page.getByTestId('event-edit-delete-btn').click();
    await expect(page.getByTestId('event-edit-modal')).not.toBeVisible();

    await page.waitForFunction(() =>
      window.__narrativeStore.getState().saveStatus !== 'Unsaved changes',
    );
    const canonicalCount = await page.evaluate(() =>
      window.__narrativeStore.getState().timelineEvents.length,
    );
    const uiCount = await nodes.count();

    expect(canonicalCount).toBe(uiCount);
  });
});

// ── Delete confirmation dialog ───────────────────────────────────────────────

test.describe('Timeline branch delete confirmation', () => {
  test.beforeEach(async ({ page }) => {
    await openTimelineWorkspace(page);
  });

  test('right-clicking a branch shows context menu with Delete option', async ({ page }) => {
    const hitArea = page.locator('[data-testid^="timeline-branch-hitarea-"]').first();
    await openBranchContextMenu(page, hitArea);
    const deleteBtn = page.locator('[data-testid^="timeline-branch-context-delete-"]').first();
    await expect(deleteBtn).toBeVisible();
  });

  test('clicking Delete in context menu shows confirmation dialog instead of deleting immediately', async ({ page }) => {
    const branch = await addEmptyBranch(page);
    await openBranchContextMenu(page, branch);

    const deleteBtn = page.locator('[data-testid^="timeline-branch-context-delete-"]').first();
    await deleteBtn.click();

    // Confirmation dialog must appear — branch must NOT be gone yet.
    await expect(page.getByTestId('timeline-delete-confirm-dialog')).toBeVisible();
    await expect(branch).toBeAttached();
  });

  test('clicking Cancel in confirmation keeps the branch', async ({ page }) => {
    const branch = await addEmptyBranch(page);
    await openBranchContextMenu(page, branch);
    const deleteBtn = page.locator('[data-testid^="timeline-branch-context-delete-"]').first();
    await deleteBtn.click();

    await expect(page.getByTestId('timeline-delete-confirm-dialog')).toBeVisible();
    await page.getByTestId('timeline-delete-confirm-cancel').click();
    await expect(page.getByTestId('timeline-delete-confirm-dialog')).not.toBeVisible();

    // Branch must still be present.
    await expect(branch).toBeAttached();
  });

  test('clicking Delete in confirmation removes the branch', async ({ page }) => {
    const branch = await addEmptyBranch(page);
    await openBranchContextMenu(page, branch);
    const deleteBtn = page.locator('[data-testid^="timeline-branch-context-delete-"]').first();
    await deleteBtn.click();

    await expect(page.getByTestId('timeline-delete-confirm-dialog')).toBeVisible();
    await page.getByTestId('timeline-delete-confirm-ok').click();
    await expect(page.getByTestId('timeline-delete-confirm-dialog')).not.toBeVisible();

    await expect(branch).toHaveCount(0);
  });

  test('clicking overlay background cancels confirmation', async ({ page }) => {
    const branch = await addEmptyBranch(page);
    await openBranchContextMenu(page, branch);
    const deleteBtn = page.locator('[data-testid^="timeline-branch-context-delete-"]').first();
    await deleteBtn.click();

    await expect(page.getByTestId('timeline-delete-confirm-overlay')).toBeVisible();
    await page.getByTestId('timeline-delete-confirm-overlay').click({ position: { x: 5, y: 5 } });
    await expect(page.getByTestId('timeline-delete-confirm-dialog')).not.toBeVisible();
  });
});
