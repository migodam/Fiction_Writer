/**
 * E2E tests for global undo / redo transaction system.
 * No live API calls. Store actions invoked directly via window.__narrativeStore.
 *
 * Covers:
 *   - updateCharacter pushes undo entry; undoAction restores previous value
 *   - moveTimelineEvent pushes undo entry; undoAction restores branch assignment
 *   - setSelectedEntity does NOT add to undo stack
 *   - redoAction re-applies change after undoAction
 */
import { expect, test } from '@playwright/test';

async function setupUndoScenario(page: import('@playwright/test').Page) {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    if (!store) throw new Error('__narrativeStore not exposed');
    store.getState().addCharacter({
      id: 'undo_char_01',
      name: '原始名字',
      summary: 'test',
      background: '',
      aliases: [],
      birthdayText: '',
      portraitAssetId: null,
      traits: '',
      goals: '',
      fears: '',
      secrets: '',
      speechStyle: '',
      arc: '',
      tagIds: [],
      organizationIds: [],
      linkedSceneIds: [],
      linkedEventIds: [],
      linkedWorldItemIds: [],
      importance: 'supporting',
      groupKey: 'supporting',
      relationshipIds: [],
      povInsights: null,
      statusFlags: { alive: true },
    });
  });
}

const UPDATED_CHAR = {
  id: 'undo_char_01',
  name: '修改后名字',
  summary: 'test',
  background: '',
  aliases: [],
  birthdayText: '',
  portraitAssetId: null,
  traits: '',
  goals: '',
  fears: '',
  secrets: '',
  speechStyle: '',
  arc: '',
  tagIds: [],
  organizationIds: [],
  linkedSceneIds: [],
  linkedEventIds: [],
  linkedWorldItemIds: [],
  importance: 'supporting',
  groupKey: 'supporting',
  relationshipIds: [],
  povInsights: null,
  statusFlags: { alive: true },
};

// Test 1: updateCharacter pushes to undo stack and undoAction restores previous state
test('updateCharacter pushes to undo stack and undoAction restores previous state', async ({ page }) => {
  await setupUndoScenario(page);

  const beforeName = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().characters.find((c: any) => c.id === 'undo_char_01')?.name,
  );
  expect(beforeName).toBe('原始名字');

  await page.evaluate((char) => {
    (window as any).__narrativeStore.getState().updateCharacter(char);
  }, UPDATED_CHAR);

  const afterName = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().characters.find((c: any) => c.id === 'undo_char_01')?.name,
  );
  expect(afterName).toBe('修改后名字');

  const undoDepth = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );
  expect(undoDepth).toBeGreaterThan(0);

  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });

  const restoredName = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().characters.find((c: any) => c.id === 'undo_char_01')?.name,
  );
  expect(restoredName).toBe('原始名字');
});

// Test 2: moveTimelineEvent pushes to undo stack and undoAction restores event branch
test('moveTimelineEvent pushes to undo stack and undoAction restores event branch', async ({ page }) => {
  await page.goto('http://localhost:3000');

  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    const branchA = {
      id: 'undo_branch_a', name: '主线', description: '', parentBranchId: null,
      forkEventId: null, mergeEventId: null, color: '#38bdf8', sortOrder: 0,
      collapsed: false, mode: 'independent' as const, startAnchor: null, endAnchor: null,
      endMode: 'open' as const, mergeTargetBranchId: null,
      anchorStartPos: { x: 0, y: 45 }, anchorEndPos: { x: 2000, y: 45 },
      geometry: { laneOffset: 0, bend: 0.25, thickness: 1 },
    };
    const branchB = {
      id: 'undo_branch_b', name: '支线', description: '', parentBranchId: null,
      forkEventId: null, mergeEventId: null, color: '#f59e0b', sortOrder: 1,
      collapsed: false, mode: 'independent' as const, startAnchor: null, endAnchor: null,
      endMode: 'open' as const, mergeTargetBranchId: null,
      anchorStartPos: { x: 0, y: 135 }, anchorEndPos: { x: 2000, y: 135 },
      geometry: { laneOffset: 90, bend: 0.25, thickness: 1 },
    };
    const event = {
      id: 'undo_evt_01', title: '测试事件', branchId: 'undo_branch_a', orderIndex: 0,
      time: '', location: '', summary: '', participantIds: [], linkedSceneId: null,
      sharedBranchIds: [], position: null, tagIds: [],
    };
    store.setState((s: any) => ({
      timelineBranches: [...s.timelineBranches, branchA, branchB],
      timelineEvents: [...s.timelineEvents, event],
    }));
  });

  const originalBranch = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().timelineEvents
      .find((e: any) => e.id === 'undo_evt_01')?.branchId,
  );
  expect(originalBranch).toBe('undo_branch_a');

  await page.evaluate(() => {
    (window as any).__narrativeStore.getState().moveTimelineEvent('undo_evt_01', 'undo_branch_b', 0);
  });

  const movedBranch = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().timelineEvents
      .find((e: any) => e.id === 'undo_evt_01')?.branchId,
  );
  expect(movedBranch).toBe('undo_branch_b');

  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });

  const restoredBranch = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().timelineEvents
      .find((e: any) => e.id === 'undo_evt_01')?.branchId,
  );
  expect(restoredBranch).toBe('undo_branch_a');
});

// Test 3: setSelectedEntity does NOT add to undo stack
test('setSelectedEntity does not create undo stack entries', async ({ page }) => {
  await page.goto('http://localhost:3000');

  const stackBefore = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );

  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.getState().setSelectedEntity('character', 'char_001');
    store.getState().setSelectedEntity('scene', 'scene_001');
    store.getState().setSelectedEntity(null, null);
  });

  const stackAfter = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  );
  expect(stackAfter).toBe(stackBefore);
});

// Test 4: redoAction re-applies change after undoAction
test('redoAction re-applies change after undoAction', async ({ page }) => {
  await setupUndoScenario(page);

  await page.evaluate((char) => {
    (window as any).__narrativeStore.getState().updateCharacter(char);
  }, UPDATED_CHAR);

  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });

  const afterUndo = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().characters
      .find((c: any) => c.id === 'undo_char_01')?.name,
  );
  expect(afterUndo).toBe('原始名字');

  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().redoAction();
  });

  const afterRedo = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().characters
      .find((c: any) => c.id === 'undo_char_01')?.name,
  );
  expect(afterRedo).toBe('修改后名字');
});

test('one Cmd/Ctrl+Z reverses exactly one of two undo entries', async ({ page }) => {
  await setupUndoScenario(page);

  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.setState({ undoStack: [], redoStack: [] });
    const character = store.getState().characters.find((entry: any) => entry.id === 'undo_char_01');
    store.getState().updateCharacter({ ...character, name: '第一次修改' });
    store.getState().updateCharacter({ ...character, name: '第二次修改' });
  });

  await expect.poll(() => page.evaluate(() => (window as any).__narrativeStore.getState().undoStack.length)).toBe(2);
  await page.keyboard.press('Control+Z');

  await expect.poll(() => page.evaluate(() => ({
    name: (window as any).__narrativeStore.getState().characters.find((entry: any) => entry.id === 'undo_char_01')?.name,
    undoDepth: (window as any).__narrativeStore.getState().undoStack.length,
    redoDepth: (window as any).__narrativeStore.getState().redoStack.length,
  }))).toEqual({ name: '第一次修改', undoDepth: 1, redoDepth: 1 });
});
