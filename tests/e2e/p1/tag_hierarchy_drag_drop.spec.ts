/**
 * E2E acceptance tests for W5 hierarchical tags and Windows-like drag/drop.
 * Navigation pattern: go to the TARGET URL first, then inject state via evaluate.
 * This avoids a second page.goto() that would wipe injected Zustand state.
 * No live API calls.
 */
import { expect, test } from '@playwright/test';

/**
 * Navigate to the given URL and inject extra state into the Zustand store.
 * Because page.goto triggers store rehydration, state is injected AFTER navigation.
 */
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

// ─── Test 1: 4-level nesting renders ─────────────────────────────────────────
test('character tag tree renders 4 levels of nesting', async ({ page }) => {
  const tags = [
    { id: 'ctag_l1', name: 'Level 1', color: '#f59e0b', description: '', characterIds: [], parentTagId: null,      sortOrder: 0 },
    { id: 'ctag_l2', name: 'Level 2', color: '#38bdf8', description: '', characterIds: [], parentTagId: 'ctag_l1', sortOrder: 0 },
    { id: 'ctag_l3', name: 'Level 3', color: '#22c55e', description: '', characterIds: [], parentTagId: 'ctag_l2', sortOrder: 0 },
    { id: 'ctag_l4', name: 'Level 4', color: '#ef4444', description: '', characterIds: [], parentTagId: 'ctag_l3', sortOrder: 0 },
  ];

  await injectAt(page, 'http://localhost:3000/characters/tags', { characterTags: tags });

  await expect(page.getByTestId('tag-tree-panel-character-tag')).toBeVisible({ timeout: 10000 });

  // All 4 levels visible via their row testids.
  for (const tag of tags) {
    await expect(page.getByTestId(`character-tag-row-${tag.id}`)).toBeVisible();
  }
});

// ─── Test 2: moveCharacterTag store action re-parents a tag ──────────────────
test('moveCharacterTag re-parents tag and tree reflects new structure', async ({ page }) => {
  const tags = [
    { id: 'ctag_root', name: 'Root',  color: '#f59e0b', description: '', characterIds: [], parentTagId: null,       sortOrder: 0 },
    { id: 'ctag_sub',  name: 'Sub',   color: '#38bdf8', description: '', characterIds: [], parentTagId: 'ctag_root', sortOrder: 0 },
    { id: 'ctag_leaf', name: 'Leaf',  color: '#22c55e', description: '', characterIds: [], parentTagId: 'ctag_sub',  sortOrder: 0 },
  ];

  await injectAt(page, 'http://localhost:3000/characters/tags', { characterTags: tags });

  // Move 'Leaf' to be a direct child of 'Root' (skip one level).
  const newParentId = await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.getState().moveCharacterTag('ctag_leaf', 'ctag_root', null);
    const updated = store.getState().characterTags;
    return updated.find((t: any) => t.id === 'ctag_leaf')?.parentTagId;
  });

  expect(newParentId).toBe('ctag_root');

  // Tree should still show all three rows.
  await expect(page.getByTestId('tag-tree-panel-character-tag')).toBeVisible();
  await expect(page.getByTestId('character-tag-row-ctag_leaf')).toBeVisible();
});

// ─── Test 3: Cycle prevention ─────────────────────────────────────────────────
test('moveCharacterTag rejects cycle and leaves state unchanged', async ({ page }) => {
  const tags = [
    { id: 'ctag_parent', name: 'Parent', color: '#f59e0b', description: '', characterIds: [], parentTagId: null,         sortOrder: 0 },
    { id: 'ctag_child',  name: 'Child',  color: '#38bdf8', description: '', characterIds: [], parentTagId: 'ctag_parent', sortOrder: 0 },
  ];

  await injectAt(page, 'http://localhost:3000/characters/tags', { characterTags: tags });

  // Attempt cycle: move Parent under Child.
  const result = await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.getState().moveCharacterTag('ctag_parent', 'ctag_child', null);
    const updated = store.getState().characterTags;
    return updated.find((t: any) => t.id === 'ctag_parent')?.parentTagId;
  });

  // parentTagId must remain null (cycle rejected).
  expect(result).toBeNull();
});

// ─── Test 4: World category tree renders ─────────────────────────────────────
test('world category tree renders with 3-level categories', async ({ page }) => {
  const worldCategories = [
    { id: 'wcat_root', name: '世界模型', parentId: null,        sortOrder: 0, scope: 'world' as const },
    { id: 'wcat_loc',  name: '地理位置', parentId: 'wcat_root', sortOrder: 0, scope: 'world' as const },
    { id: 'wcat_city', name: '城镇',     parentId: 'wcat_loc',  sortOrder: 0, scope: 'world' as const },
  ];

  await injectAt(page, 'http://localhost:3000/world', { worldCategories });

  await expect(page.getByTestId('world-category-tree-toggle')).toBeVisible({ timeout: 10000 });

  // Tree is visible by default.
  await expect(page.getByTestId('world-category-tree')).toBeVisible();

  // The virtual World root is hidden in the Folder UI; its children are promoted.
  await expect(page.getByTestId('world-category-node-wcat_root')).not.toBeVisible();
  await expect(page.getByTestId('world-category-node-wcat_loc')).toBeVisible();
  await expect(page.getByTestId('world-category-node-wcat_city')).toBeVisible();
});

// ─── Test 5: World category cycle prevention ──────────────────────────────────
test('moveWorldCategory rejects cycle and leaves world categories unchanged', async ({ page }) => {
  const worldCategories = [
    { id: 'wcat_a', name: 'A', parentId: null,      sortOrder: 0, scope: 'world' as const },
    { id: 'wcat_b', name: 'B', parentId: 'wcat_a',  sortOrder: 0, scope: 'world' as const },
    { id: 'wcat_c', name: 'C', parentId: 'wcat_b',  sortOrder: 0, scope: 'world' as const },
  ];

  await injectAt(page, 'http://localhost:3000/world', { worldCategories });

  // Attempt cycle: move A (root) under C (its own grandchild).
  const result = await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.getState().moveWorldCategory('wcat_a', 'wcat_c', null);
    const updated = store.getState().worldCategories;
    return updated.find((n: any) => n.id === 'wcat_a')?.parentId;
  });

  // A's parentId must remain null.
  expect(result).toBeNull();
});
