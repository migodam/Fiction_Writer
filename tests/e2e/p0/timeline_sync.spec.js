import { test, expect } from '@playwright/test';
import path from 'path';
import fs from 'fs';

// ── Helpers ──────────────────────────────────────────────────────────────────

async function openTimelineWorkspace(page) {
  await page.goto('/');
  await page.getByTestId('activity-btn-timeline').click();
  await expect(page.getByTestId('timeline-canvas')).toBeVisible();
}

// Locate the active project's timeline directory by reading the app's title bar
// or by using the known test project path that Playwright uses.
function getTimelineDir() {
  // The Playwright fixture project is the starter-demo-project used in dev.
  const root = path.resolve('data/projects/starter-demo-project/entities/timeline');
  return root;
}

function listEventFiles(timelineDir) {
  if (!fs.existsSync(timelineDir)) return [];
  return fs.readdirSync(timelineDir).filter((f) => f !== 'branches.json' && f.endsWith('.json'));
}

// ── Sync bug: orphan cleanup ──────────────────────────────────────────────────

test.describe('Timeline sync — orphan file cleanup', () => {
  test('deleting a timeline event removes its JSON file on save', async ({ page }) => {
    const timelineDir = getTimelineDir();
    const filesBefore = listEventFiles(timelineDir);

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

    // Trigger a save by waiting for the autosave or forcing one via keyboard shortcut.
    // The app autosaves on state change, but we give it a moment.
    await page.waitForTimeout(2000);

    // Verify the orphaned file no longer exists on disk.
    const orphanFile = path.join(timelineDir, `${eventId}.json`);
    expect(
      fs.existsSync(orphanFile),
      `Orphaned event file should have been deleted: ${orphanFile}`
    ).toBe(false);

    // Verify the set of files decreased by exactly one.
    const filesAfter = listEventFiles(timelineDir);
    expect(filesAfter.length).toBe(filesBefore.length - 1);
  });

  test('file count on disk matches frontend event count after multiple deletions', async ({ page }) => {
    await openTimelineWorkspace(page);

    const nodes = page.locator('[data-testid^="timeline-event-node-"]');
    const initialCount = await nodes.count();
    if (initialCount < 2) test.skip(); // need at least 2 events

    // Delete the first event.
    await nodes.first().click();
    await expect(page.getByTestId('event-edit-modal')).toBeVisible();
    await page.getByTestId('event-edit-delete-btn').click();
    await expect(page.getByTestId('event-edit-modal')).not.toBeVisible();

    // Wait for autosave.
    await page.waitForTimeout(2000);

    const timelineDir = getTimelineDir();
    const diskCount = listEventFiles(timelineDir).length;
    const uiCount = await nodes.count();

    expect(diskCount).toBe(uiCount);
  });
});

// ── Delete confirmation dialog ───────────────────────────────────────────────

test.describe('Timeline branch delete confirmation', () => {
  test.beforeEach(async ({ page }) => {
    await openTimelineWorkspace(page);
  });

  test('right-clicking a branch shows context menu with Delete option', async ({ page }) => {
    const hitArea = page.locator('[data-testid^="timeline-branch-hitarea-"]').first();
    await expect(hitArea).toBeVisible();
    await hitArea.click({ button: 'right' });
    await expect(page.getByTestId('timeline-branch-context-menu')).toBeVisible();
    const deleteBtn = page.locator('[data-testid^="timeline-branch-context-delete-"]').first();
    await expect(deleteBtn).toBeVisible();
  });

  test('clicking Delete in context menu shows confirmation dialog instead of deleting immediately', async ({ page }) => {
    const branches = page.locator('[data-testid^="timeline-branch-hitarea-"]');
    const branchCount = await branches.count();
    if (branchCount === 0) test.skip();

    await branches.first().click({ button: 'right' });
    await expect(page.getByTestId('timeline-branch-context-menu')).toBeVisible();

    const deleteBtn = page.locator('[data-testid^="timeline-branch-context-delete-"]').first();
    await deleteBtn.click();

    // Confirmation dialog must appear — branch must NOT be gone yet.
    await expect(page.getByTestId('timeline-delete-confirm-dialog')).toBeVisible();
    await expect(branches.first()).toBeVisible();
  });

  test('clicking Cancel in confirmation keeps the branch', async ({ page }) => {
    const branches = page.locator('[data-testid^="timeline-branch-hitarea-"]');
    if (await branches.count() === 0) test.skip();

    await branches.first().click({ button: 'right' });
    const deleteBtn = page.locator('[data-testid^="timeline-branch-context-delete-"]').first();
    await deleteBtn.click();

    await expect(page.getByTestId('timeline-delete-confirm-dialog')).toBeVisible();
    await page.getByTestId('timeline-delete-confirm-cancel').click();
    await expect(page.getByTestId('timeline-delete-confirm-dialog')).not.toBeVisible();

    // Branch must still be present.
    await expect(branches.first()).toBeVisible();
  });

  test('clicking Delete in confirmation removes the branch', async ({ page }) => {
    const branches = page.locator('[data-testid^="timeline-branch-hitarea-"]');
    const before = await branches.count();
    if (before === 0) test.skip();

    await branches.first().click({ button: 'right' });
    const deleteBtn = page.locator('[data-testid^="timeline-branch-context-delete-"]').first();
    await deleteBtn.click();

    await expect(page.getByTestId('timeline-delete-confirm-dialog')).toBeVisible();
    await page.getByTestId('timeline-delete-confirm-ok').click();
    await expect(page.getByTestId('timeline-delete-confirm-dialog')).not.toBeVisible();

    // Branch count must have decreased.
    await expect(branches).toHaveCount(before - 1);
  });

  test('clicking overlay background cancels confirmation', async ({ page }) => {
    const branches = page.locator('[data-testid^="timeline-branch-hitarea-"]');
    if (await branches.count() === 0) test.skip();

    await branches.first().click({ button: 'right' });
    const deleteBtn = page.locator('[data-testid^="timeline-branch-context-delete-"]').first();
    await deleteBtn.click();

    await expect(page.getByTestId('timeline-delete-confirm-overlay')).toBeVisible();
    await page.getByTestId('timeline-delete-confirm-overlay').click({ position: { x: 5, y: 5 } });
    await expect(page.getByTestId('timeline-delete-confirm-dialog')).not.toBeVisible();
  });
});
