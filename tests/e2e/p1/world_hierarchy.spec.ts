/**
 * E2E tests for WorldWorkspace hierarchy grouping and contamination filtering.
 * No live API calls. Fixtures injected via window.__narrativeStore.
 *
 * Covers:
 *   - Category group headers render for items with categoryPath
 *   - Contamination containers (人物关系图, 事件时间线) not visible in container list
 *   - Items without categoryPath render flat (no group header)
 *   - Items without categoryPath still render (flat fallback)
 */
import { expect, test } from '@playwright/test';

const FIXTURE_CONTAINERS = [
  { id: 'wcont_main', name: '功法与术法', type: 'notebook' as const, sortOrder: 0, importCategoryKey: 'cultivation_methods' },
  { id: 'wcont_loc', name: '地理位置', type: 'notebook' as const, sortOrder: 1, importCategoryKey: 'locations' },
  { id: 'wcont_contam1', name: '人物关系图', type: 'graph' as const, sortOrder: 2 },
  { id: 'wcont_contam2', name: '事件时间线', type: 'timeline' as const, sortOrder: 3 },
];

const FIXTURE_ITEMS = [
  {
    id: 'wi_01', containerId: 'wcont_main', type: 'cultivation_method', name: '长春功',
    description: '基础功法', attributes: [], linkedCharacterIds: [], linkedEventIds: [],
    linkedSceneIds: [], mapMarkers: [], tagIds: [],
    categoryPath: ['世界模型', '功法与术法', '长春功'], parentId: null,
  },
  {
    id: 'wi_02', containerId: 'wcont_main', type: 'cultivation_method', name: '吐雾七式',
    description: '七式攻击法', attributes: [], linkedCharacterIds: [], linkedEventIds: [],
    linkedSceneIds: [], mapMarkers: [], tagIds: [],
    categoryPath: ['世界模型', '功法与术法', '吐雾七式'], parentId: null,
  },
  {
    id: 'wi_03', containerId: 'wcont_loc', type: 'location', name: '神手谷',
    description: '炼器之地', attributes: [], linkedCharacterIds: [], linkedEventIds: [],
    linkedSceneIds: [], mapMarkers: [], tagIds: [],
    categoryPath: ['世界模型', '地理位置', '神手谷'], parentId: null,
  },
];

async function injectWorldFixture(page: import('@playwright/test').Page) {
  await page.goto('http://localhost:3000');
  await page.evaluate(({ containers, items }) => {
    const store = (window as any).__narrativeStore;
    if (!store) throw new Error('__narrativeStore not exposed');
    store.setState((s: any) => ({
      worldContainers: [...s.worldContainers, ...containers],
      worldItems: [...s.worldItems, ...items],
    }));
  }, { containers: FIXTURE_CONTAINERS, items: FIXTURE_ITEMS });
}

// Test 1: category group headers render for items with categoryPath
test('world items with categoryPath render under group headers', async ({ page }) => {
  await injectWorldFixture(page);
  await page.getByTestId('activity-btn-world').click();

  await page.getByTestId('world-container-wcont_main').click();
  await expect(page.getByTestId('world-item-list')).toBeVisible();

  await expect(page.getByTestId('world-category-group-功法与术法')).toBeVisible();
  await expect(page.getByTestId('world-item-wi_01')).toBeVisible();
  await expect(page.getByTestId('world-item-wi_02')).toBeVisible();
});

// Test 2: contamination containers not shown in container list
test('contamination containers are not shown in world container list', async ({ page }) => {
  await injectWorldFixture(page);
  await page.getByTestId('activity-btn-world').click();
  await expect(page.getByTestId('world-container-list')).toBeVisible();

  await expect(page.getByTestId('world-container-wcont_contam1')).not.toBeVisible();
  await expect(page.getByTestId('world-container-wcont_contam2')).not.toBeVisible();
  await expect(page.getByTestId('world-container-wcont_main')).toBeVisible();
});

// Test 3: items WITHOUT categoryPath show flat without group header
test('items without categoryPath show flat without group header', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    const cont = { id: 'wcont_flat', name: '旧数据', type: 'notebook' as const, sortOrder: 99 };
    const items = [
      {
        id: 'wflat_01', containerId: 'wcont_flat', type: 'concept', name: '旧功法',
        description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [],
        linkedSceneIds: [], mapMarkers: [], tagIds: [],
      },
    ];
    store.setState((s: any) => ({
      worldContainers: [...s.worldContainers, cont],
      worldItems: [...s.worldItems, ...items],
    }));
  });
  await page.getByTestId('activity-btn-world').click();
  await page.getByTestId('world-container-wcont_flat').click();
  await expect(page.getByTestId('world-item-list')).toBeVisible();

  await expect(page.getByTestId('world-item-wflat_01')).toBeVisible();
  const groupHeaders = page.locator('[data-testid^="world-category-group-"]');
  await expect(groupHeaders).toHaveCount(0);
});

// Test 4: items without categoryPath still render (flat fallback, not silently dropped)
test('items without categoryPath still render in flat fallback mode', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    const store = (window as any).__narrativeStore;
    const cont = { id: 'wcont_legacy', name: '旧世界', type: 'notebook' as const, sortOrder: 97 };
    const items = [
      {
        id: 'wlegacy_01', containerId: 'wcont_legacy', type: 'organization', name: '旧门派',
        description: '旧格式无categoryPath', attributes: [], linkedCharacterIds: [],
        linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], tagIds: [],
        category: 'organization',
      },
      {
        id: 'wlegacy_02', containerId: 'wcont_legacy', type: 'location', name: '旧地点',
        description: '', attributes: [], linkedCharacterIds: [],
        linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], tagIds: [],
        category: 'location',
      },
    ];
    store.setState((s: any) => ({
      worldContainers: [...s.worldContainers, cont],
      worldItems: [...s.worldItems, ...items],
    }));
  });
  await page.getByTestId('activity-btn-world').click();
  await page.getByTestId('world-container-wcont_legacy').click();
  await expect(page.getByTestId('world-item-list')).toBeVisible();

  await expect(page.getByTestId('world-item-wlegacy_01')).toBeVisible();
  await expect(page.getByTestId('world-item-wlegacy_02')).toBeVisible();
});

// Test 5: children of hidden wcat_root are promoted to top-level in the category tree
test('children of hidden wcat_root are visible as top-level nodes in TagTreePanel', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState((s: any) => ({
      worldCategories: [
        { id: 'wcat_root', name: '世界模型', parentId: null, sortOrder: 0, scope: 'world' },
        { id: 'wcat_child', name: '功法类型', parentId: 'wcat_root', sortOrder: 0, scope: 'world' },
        { id: 'wcat_sib', name: '地理', parentId: 'wcat_root', sortOrder: 1, scope: 'world' },
      ],
      worldContainers: [
        ...s.worldContainers,
        { id: 'wc_vis_test', name: '可见测试', type: 'notebook' as const, sortOrder: 80 },
      ],
    }));
  });
  await page.getByTestId('activity-btn-world').click();
  await page.getByTestId('world-container-wc_vis_test').click();

  // Hidden root must not appear
  await expect(page.getByTestId('world-category-node-wcat_root')).not.toBeVisible();
  // Its children must be visible as top-level
  await expect(page.getByTestId('world-category-node-wcat_child')).toBeVisible();
  await expect(page.getByTestId('world-category-node-wcat_sib')).toBeVisible();
});

// Test 6: categoryId-based item filter uses stable ID not display string
test('selecting category by ID filters items using categoryId field', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState((s: any) => ({
      worldContainers: [
        ...s.worldContainers,
        { id: 'wc_idtest', name: '测试容器', type: 'notebook' as const, sortOrder: 90 },
      ],
      worldItems: [
        ...s.worldItems,
        {
          id: 'wi_match', containerId: 'wc_idtest', type: 'concept', name: '属于功法',
          description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [],
          linkedSceneIds: [], mapMarkers: [], tagIds: [],
          categoryId: 'wcat_stable', categoryPath: ['世界模型', '功法类型'],
        },
        {
          id: 'wi_other', containerId: 'wc_idtest', type: 'concept', name: '不属于',
          description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [],
          linkedSceneIds: [], mapMarkers: [], tagIds: [],
          categoryId: 'wcat_other', categoryPath: ['世界模型', '其他'],
        },
      ],
      worldCategories: [
        { id: 'wcat_stable', name: '功法类型', parentId: null, sortOrder: 0, scope: 'world' },
        { id: 'wcat_other', name: '其他', parentId: null, sortOrder: 1, scope: 'world' },
      ],
    }));
  });
  await page.getByTestId('activity-btn-world').click();
  await page.getByTestId('world-container-wc_idtest').click();
  await page.getByTestId('world-category-node-wcat_stable').click();
  await expect(page.getByTestId('world-item-wi_match')).toBeVisible();
  await expect(page.getByTestId('world-item-wi_other')).not.toBeVisible();
});

// Test 7: addWorldCategory creates exactly one undo entry and is reversible
test('addWorldCategory creates one undo entry and is reversible', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState({ undoStack: [], redoStack: [], pendingUndoTransaction: null });
  });
  const stackBefore = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length);
  await page.evaluate(() => {
    (window as any).__narrativeStore.getState().addWorldCategory(
      { id: 'wcat_new_u', name: '新类别', parentId: null, sortOrder: 0, scope: 'world' },
    );
  });
  const stackAfter = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length);
  expect(stackAfter).toBe(stackBefore + 1);
  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });
  const catExists = await page.evaluate(() =>
    !!(window as any).__narrativeStore.getState().worldCategories.find((c: any) => c.id === 'wcat_new_u'));
  expect(catExists).toBe(false);
});

// Test 8: moveWorldCategory creates exactly one undo entry and is reversible
test('moveWorldCategory creates one undo entry and is reversible', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState({
      undoStack: [], redoStack: [], pendingUndoTransaction: null,
      worldCategories: [
        { id: 'wcat_u_a', name: '类别A', parentId: null, sortOrder: 0, scope: 'world' },
        { id: 'wcat_u_b', name: '类别B', parentId: null, sortOrder: 1, scope: 'world' },
      ],
    });
  });
  const stackBefore = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length);
  await page.evaluate(() => {
    (window as any).__narrativeStore.getState().moveWorldCategory('wcat_u_b', 'wcat_u_a', null);
  });
  expect(await page.evaluate(() =>
    (window as any).__narrativeStore.getState().undoStack.length,
  )).toBe(stackBefore + 1);
  await page.evaluate(async () => {
    await (window as any).__narrativeStore.getState().undoAction();
  });
  const catB = await page.evaluate(() =>
    (window as any).__narrativeStore.getState().worldCategories.find((c: any) => c.id === 'wcat_u_b'));
  expect(catB?.parentId).toBeNull();
});
