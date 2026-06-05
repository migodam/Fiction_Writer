/**
 * E2E tests for timeline undo transaction model (W5).
 * Verifies that branch drag operations are batched into a single undo entry
 * via beginUndoTransaction / commitUndoTransaction / cancelUndoTransaction.
 *
 * All tests use store API directly via window.__narrativeStore.
 * UI-level pointer drag is not tested here (flaky in headless); see report for coverage note.
 */
import { expect, test } from '@playwright/test';

const BASE_BRANCH = {
  id: 'tx_branch_a',
  name: '主线',
  description: '',
  parentBranchId: null,
  forkEventId: null,
  mergeEventId: null,
  color: '#38bdf8',
  sortOrder: 0,
  collapsed: false,
  mode: 'independent' as const,
  startAnchor: null,
  endAnchor: null,
  endMode: 'open' as const,
  mergeTargetBranchId: null,
  anchorStartPos: { x: 0, y: 45 },
  anchorEndPos: { x: 2000, y: 45 },
  geometry: { laneOffset: 0, bend: 0.25, thickness: 1 },
};

const BASE_EVENT = {
  id: 'tx_evt_01',
  title: '测试事件',
  branchId: 'tx_branch_a',
  orderIndex: 0,
  time: '',
  location: '',
  summary: '',
  participantIds: [],
  linkedSceneId: null,
  sharedBranchIds: [],
  position: null,
  tagIds: [],
};

async function injectAt(
  page: import('@playwright/test').Page,
  url: string,
  extra: Record<string, unknown>,
) {
  await page.goto(url);
  await page.evaluate((extra) => {
    const store = (window as any).__narrativeStore;
    if (!store) throw new Error('__narrativeStore not exposed');
    store.setState((state: any) => ({ ...state, ...extra }));
  }, extra);
}

// ─── Test 1: branch drag transaction batches into ONE undo entry ──────────────
test('branch drag creates exactly one undo entry', async ({ page }) => {
  await injectAt(page, 'http://localhost:3000/timeline', {
    timelineBranches: [BASE_BRANCH],
    timelineEvents: [BASE_EVENT],
  });

  const stackBefore = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  // Simulate a drag: beginTransaction + multiple geometry updates
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.getState().beginUndoTransaction('Adjust branch');
    store.getState().setTimelineBranchGeometry('tx_branch_a', { laneOffset: 10, bend: 0.3, thickness: 1 });
    store.getState().setTimelineBranchGeometry('tx_branch_a', { laneOffset: 20, bend: 0.4, thickness: 1 });
    store.getState().setTimelineBranchGeometry('tx_branch_a', { laneOffset: 30, bend: 0.5, thickness: 1 });
    store.getState().commitUndoTransaction();
  });

  const stackAfter = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  // Exactly one entry pushed
  expect(stackAfter).toBe(stackBefore + 1);

  // Undo restores pre-drag geometry
  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });

  const restoredGeometry = await page.evaluate(() => {
    const branch = (window as any).__narrativeStore.getState()
      .timelineBranches.find((b: any) => b.id === 'tx_branch_a');
    return branch?.geometry;
  });

  expect(restoredGeometry?.laneOffset).toBe(0);
  expect(restoredGeometry?.bend).toBe(0.25);
});

// ─── Test 2: cancelUndoTransaction leaves undo stack unchanged ────────────────
test('cancelUndoTransaction leaves undo stack unchanged', async ({ page }) => {
  await injectAt(page, 'http://localhost:3000/timeline', {
    timelineBranches: [BASE_BRANCH],
    timelineEvents: [BASE_EVENT],
  });

  const stackBefore = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.getState().beginUndoTransaction('Adjust branch');
    store.getState().setTimelineBranchGeometry('tx_branch_a', { laneOffset: 50, bend: 0.6, thickness: 1 });
    store.getState().setTimelineBranchGeometry('tx_branch_a', { laneOffset: 80, bend: 0.7, thickness: 1 });
    store.getState().cancelUndoTransaction();
  });

  const stackAfter = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  expect(stackAfter).toBe(stackBefore);
});

// ─── Test 3: post-import timeline drag pushes only one undo entry ─────────────
test('post-import timeline drag pushes only one undo entry', async ({ page }) => {
  const chapter = {
    id: 'tx_chap_01',
    title: '第一章',
    summary: '',
    sceneIds: [],
    order: 0,
    wordCountTarget: 0,
    createdAt: new Date().toISOString(),
  };

  await injectAt(page, 'http://localhost:3000/timeline', {
    timelineBranches: [BASE_BRANCH],
    timelineEvents: [BASE_EVENT],
    chapters: [chapter],
  });

  // Simulate accepting a large proposal batch (one undo entry for import)
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.getState().captureUndoSnapshot('Resolve all proposals');
  });

  const stackAfterImport = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  // Simulate a branch drag
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.getState().beginUndoTransaction('Adjust branch');
    store.getState().setTimelineBranchGeometry('tx_branch_a', { laneOffset: 15, bend: 0.35, thickness: 1 });
    store.getState().setTimelineBranchGeometry('tx_branch_a', { laneOffset: 25, bend: 0.4, thickness: 1 });
    store.getState().commitUndoTransaction();
  });

  const stackAfterDrag = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  // Exactly one new entry (not multiple geometry snapshots)
  expect(stackAfterDrag).toBe(stackAfterImport + 1);

  // Undo once → only branch geometry reverted; chapters untouched
  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });

  const chaptersAfterUndo = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().chapters,
  );
  expect(chaptersAfterUndo.find((c: any) => c.id === 'tx_chap_01')).toBeTruthy();
});

// ─── Test 4: anchor drag batches; non-timeline data untouched ─────────────────
test('anchor drag batches into one entry and non-timeline data is untouched', async ({ page }) => {
  const chapter = {
    id: 'tx_chap_02',
    title: '第二章',
    summary: '',
    sceneIds: [],
    order: 0,
    wordCountTarget: 0,
    createdAt: new Date().toISOString(),
  };
  const branchWithAnchors = {
    ...BASE_BRANCH,
    id: 'tx_branch_b',
    anchorStartPos: { x: 0, y: 90 },
    anchorEndPos: { x: 2000, y: 90 },
  };

  await injectAt(page, 'http://localhost:3000/timeline', {
    timelineBranches: [BASE_BRANCH, branchWithAnchors],
    timelineEvents: [BASE_EVENT],
    chapters: [chapter],
  });

  const stackBefore = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.getState().beginUndoTransaction('Anchor branch');
    store.getState().setTimelineBranchAnchors('tx_branch_b', { x: 10, y: 90 }, { x: 2000, y: 90 }, {});
    store.getState().setTimelineBranchAnchors('tx_branch_b', { x: 20, y: 90 }, { x: 2000, y: 90 }, {});
    store.getState().setTimelineBranchAnchors('tx_branch_b', { x: 30, y: 90 }, { x: 2000, y: 90 }, {});
    store.getState().commitUndoTransaction();
  });

  const stackAfter = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );
  expect(stackAfter).toBe(stackBefore + 1);

  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });

  // Non-timeline data (chapters) should still be present after undo
  const chaptersAfterUndo = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().chapters,
  );
  expect(chaptersAfterUndo.find((c: any) => c.id === 'tx_chap_02')).toBeTruthy();
});

// ─── Test 5: moveTimelineEvent still works (regression guard) ─────────────────
test('moveTimelineEvent undo still works after transaction API added', async ({ page }) => {
  const branchB = {
    ...BASE_BRANCH,
    id: 'tx_branch_c',
    name: '支线',
    anchorStartPos: { x: 0, y: 135 },
    anchorEndPos: { x: 2000, y: 135 },
    geometry: { laneOffset: 90, bend: 0.25, thickness: 1 },
  };

  await injectAt(page, 'http://localhost:3000/timeline', {
    timelineBranches: [BASE_BRANCH, branchB],
    timelineEvents: [BASE_EVENT],
  });

  await page.evaluate(() => {
    (window as any).__narrativeStore.getState().moveTimelineEvent('tx_evt_01', 'tx_branch_c', 0);
  });

  const movedBranch = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().timelineEvents
      .find((e: any) => e.id === 'tx_evt_01')?.branchId,
  );
  expect(movedBranch).toBe('tx_branch_c');

  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });

  const restoredBranch = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().timelineEvents
      .find((e: any) => e.id === 'tx_evt_01')?.branchId,
  );
  expect(restoredBranch).toBe('tx_branch_a');
});

// ─── Test 6: commit with no actual change is a no-op (Guard 2) ───────────────
test('commit with no actual geometry change does not push undo entry', async ({ page }) => {
  await injectAt(page, 'http://localhost:3000/timeline', {
    timelineBranches: [BASE_BRANCH],
    timelineEvents: [BASE_EVENT],
  });

  const stackBefore = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  // begin + immediately commit (no geometry mutation in between)
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.getState().beginUndoTransaction('Adjust branch');
    store.getState().commitUndoTransaction();
  });

  const stackAfter = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  expect(stackAfter).toBe(stackBefore);
});

// ─── Test 7: nested beginUndoTransaction is a no-op (Guard 1) ────────────────
test('nested beginUndoTransaction preserves original snapshot', async ({ page }) => {
  await injectAt(page, 'http://localhost:3000/timeline', {
    timelineBranches: [BASE_BRANCH],
    timelineEvents: [BASE_EVENT],
  });

  // Record original geometry for comparison
  const originalGeometry = await page.evaluate(() => {
    const branch = (window as any).__narrativeStore.getState()
      .timelineBranches.find((b: any) => b.id === 'tx_branch_a');
    return { laneOffset: branch?.geometry?.laneOffset, bend: branch?.geometry?.bend };
  });

  const stackBefore = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    // First transaction — captures pre-drag snapshot
    store.getState().beginUndoTransaction('Adjust branch');
    store.getState().setTimelineBranchGeometry('tx_branch_a', { laneOffset: 40, bend: 0.45, thickness: 1 });
    // Nested begin — must be ignored; original snapshot preserved
    store.getState().beginUndoTransaction('Nested attempt');
    store.getState().setTimelineBranchGeometry('tx_branch_a', { laneOffset: 60, bend: 0.55, thickness: 1 });
    store.getState().commitUndoTransaction();
  });

  const stackAfter = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  // Only one entry pushed (from the first transaction)
  expect(stackAfter).toBe(stackBefore + 1);

  // Undo restores to the pre-first-begin state (not post-first-begin)
  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });

  const restoredGeometry = await page.evaluate(() => {
    const branch = (window as any).__narrativeStore.getState()
      .timelineBranches.find((b: any) => b.id === 'tx_branch_a');
    return { laneOffset: branch?.geometry?.laneOffset, bend: branch?.geometry?.bend };
  });

  expect(restoredGeometry.laneOffset).toBe(originalGeometry.laneOffset);
  expect(restoredGeometry.bend).toBe(originalGeometry.bend);
});
