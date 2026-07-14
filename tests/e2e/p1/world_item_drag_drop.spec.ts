/**
 * E2E tests for world item drag/drop and moveWorldItemToCategory.
 * No live API calls. Store state injected via window.__narrativeStore.
 *
 * Covers:
 *   - moveWorldItemToCategory updates containerId, category, categoryPath
 *   - moveWorldItemToCategory is undoable (undoAction restores original container)
 *   - World item rows are draggable (drag handle present in DOM)
 */
import { expect, test } from '@playwright/test';

const FIXTURE_CONTAINERS = [
  {
    id: 'wc_rules',
    name: '修炼境界与制度',
    type: 'notebook' as const,
    sortOrder: 0,
    importCategoryKey: 'rules',
  },
  {
    id: 'wc_methods',
    name: '功法与术法',
    type: 'notebook' as const,
    sortOrder: 1,
    importCategoryKey: 'cultivation_methods',
  },
];

const FIXTURE_ITEMS = [
  {
    id: 'wi_xjg',
    containerId: 'wc_rules',
    type: 'rule',
    name: '项甲功',
    description: '一种基础功法',
    attributes: [],
    linkedCharacterIds: [],
    linkedEventIds: [],
    linkedSceneIds: [],
    mapMarkers: [],
    tagIds: [],
    categoryPath: ['世界模型', '修炼境界与制度', '项甲功'],
    parentId: null,
  },
];

async function injectFixture(page: import('@playwright/test').Page) {
  await page.goto('http://localhost:3000');
  await page.evaluate(
    ({ containers, items }) => {
      const store = (window as any).__narrativeStore;
      if (!store) throw new Error('__narrativeStore not exposed');
      store.setState((s: any) => ({
      worldContainers: [...s.worldContainers, ...containers],
      worldItems: [...s.worldItems, ...items],
      undoStack: [],
      redoStack: [],
      }));
    },
    { containers: FIXTURE_CONTAINERS, items: FIXTURE_ITEMS },
  );
}

// Test 1: moveWorldItemToCategory updates containerId, category, categoryPath
test('moveWorldItemToCategory store action moves item to new container', async ({ page }) => {
  await injectFixture(page);

  const before = await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    return store.getState().worldItems.find((i: any) => i.id === 'wi_xjg');
  });
  expect(before.containerId).toBe('wc_rules');
  expect(before.categoryPath[1]).toBe('修炼境界与制度');

  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.getState().moveWorldItemToCategory(
      'wi_xjg',
      'cultivation_method',
      'wc_methods',
      ['世界模型', '功法与术法', '项甲功'],
    );
  });

  const after = await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    return store.getState().worldItems.find((i: any) => i.id === 'wi_xjg');
  });
  expect(after.containerId).toBe('wc_methods');
  expect(after.category).toBe('cultivation_method');
  expect(after.categoryPath[1]).toBe('功法与术法');
});

// Test 2: moveWorldItemToCategory is undoable
test('moveWorldItemToCategory retains references and is one undo transaction', async ({ page }) => {
  await injectFixture(page);

  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    store.setState((state: any) => ({
      characters: [...state.characters, { id: 'wi_ref_char', linkedWorldItemIds: ['wi_xjg'] }],
      timelineEvents: [...state.timelineEvents, { id: 'wi_ref_event', locationIds: ['wi_xjg'], linkedWorldItemIds: ['wi_xjg'] }],
      scenes: [...state.scenes, { id: 'wi_ref_scene', linkedWorldItemIds: ['wi_xjg'] }],
    }));
  });

  await page.evaluate(() => {
    (window as any).__narrativeStore.getState().moveWorldItemToCategory(
      'wi_xjg',
      'cultivation_method',
      'wc_methods',
      ['世界模型', '功法与术法', '项甲功'],
    );
  });

  await expect.poll(() => page.evaluate(() => (window as any).__narrativeStore.getState().undoStack.length)).toBe(1);
  await expect.poll(() => page.evaluate(() => {
    const state = (window as any).__narrativeStore.getState();
    return {
      count: state.worldItems.filter((item: any) => item.id === 'wi_xjg').length,
      character: state.characters.find((item: any) => item.id === 'wi_ref_char').linkedWorldItemIds,
      event: state.timelineEvents.find((item: any) => item.id === 'wi_ref_event'),
      scene: state.scenes.find((item: any) => item.id === 'wi_ref_scene').linkedWorldItemIds,
    };
  })).toEqual({
    count: 1,
    character: ['wi_xjg'],
    event: { id: 'wi_ref_event', locationIds: ['wi_xjg'], linkedWorldItemIds: ['wi_xjg'] },
    scene: ['wi_xjg'],
  });

  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });

  const restored = await page.evaluate(() => {
    return (window as any).__narrativeStore.getState().worldItems.find((i: any) => i.id === 'wi_xjg');
  });
  expect(restored.containerId).toBe('wc_rules');
  expect(restored.categoryPath[1]).toBe('修炼境界与制度');
  await expect.poll(() => page.evaluate(() => (window as any).__narrativeStore.getState().undoStack.length)).toBe(0);
});

// Test 3: World item rows show drag handle in DOM
test('world item rows are draggable — drag handle present in DOM', async ({ page }) => {
  await injectFixture(page);
  await page.getByTestId('activity-btn-world').click();
  await page.getByTestId('world-container-wc_rules').click();
  await expect(page.getByTestId('world-item-list')).toBeVisible();

  // Item should be visible in its original container
  await expect(page.getByTestId('world-item-wi_xjg')).toBeVisible();

  // Hover to reveal drag handle, then check it's attached
  await page.getByTestId('world-item-wi_xjg').hover();
  await expect(page.getByTestId('world-item-wi_xjg').locator('svg').first()).toBeAttached();
});
