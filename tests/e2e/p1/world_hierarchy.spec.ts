import { expect, test } from '@playwright/test';

const notebooks = [
  { id: 'nb_world', name: '世界模型', type: 'notebook' as const, sortOrder: 0, parentId: null, isCollapsed: false },
  { id: 'folder_places', name: '世界地理', type: 'notebook' as const, sortOrder: 1, parentId: 'nb_world', isCollapsed: false },
  { id: 'folder_buildings', name: '建筑', type: 'notebook' as const, sortOrder: 2, parentId: 'folder_places', isCollapsed: false },
];

const items = [
  { id: 'wi_gate', folderId: 'folder_buildings', containerId: 'nb_world', type: 'location', name: '正门', description: '七玄门入口', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], tagIds: [] },
  { id: 'wi_legacy', containerId: 'folder_places', type: 'location', name: '旧地点', description: '从旧 containerId 迁移', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], tagIds: [] },
];

async function installFixture(page: import('@playwright/test').Page) {
  await page.goto('http://localhost:3000');
  await page.evaluate(({ notebooks, items }) => {
    (window as any).__narrativeStore.setState((state: any) => ({
      ...state,
      worldContainers: notebooks,
      worldItems: items,
      worldCategories: [{ id: 'legacy_category', name: '不应参与展示', parentId: null, sortOrder: 0, scope: 'world' }],
    }));
  }, { notebooks, items });
  await page.getByTestId('activity-btn-world').click();
}

test('World Model is a notebook and folder tree, not a categoryPath projection', async ({ page }) => {
  await installFixture(page);
  await expect(page.getByTestId('world-notebook-workspace')).toBeVisible();
  await expect(page.getByTestId('world-container-nb_world')).toContainText('世界模型');
  await expect(page.getByTestId('world-folder-nb_world')).toBeVisible();
  await expect(page.getByTestId('world-folder-folder_places')).toBeVisible();
  await expect(page.getByTestId('world-folder-folder_buildings')).toBeVisible();
  await expect(page.getByTestId('world-category-tree')).toHaveCount(0);
});

test('legacy containerId is read as the compatible folder owner and new moves write folderId', async ({ page }) => {
  await installFixture(page);
  await page.getByTestId('world-folder-folder_places').click();
  await expect(page.getByTestId('world-item-wi_legacy')).toBeVisible();
  await page.evaluate(() => (window as any).__narrativeStore.getState().moveWorldItem('wi_legacy', 'folder_buildings'));
  const moved = await page.evaluate(() => (window as any).__narrativeStore.getState().worldItems.find((item: any) => item.id === 'wi_legacy'));
  expect(moved.folderId).toBe('folder_buildings');
  expect(moved.containerId).toBe('folder_buildings');
});

test('folder drop target and move action use the folder ID as the canonical owner', async ({ page }) => {
  await installFixture(page);
  await page.getByTestId('world-folder-folder_places').click();
  await expect(page.getByTestId('world-item-drag-handle-wi_legacy')).toBeVisible();
  await expect(page.getByTestId('world-folder-drop-folder_buildings')).toBeVisible();
  await page.evaluate(() => (window as any).__narrativeStore.getState().moveWorldItem('wi_legacy', 'folder_buildings'));
  await expect.poll(() => page.evaluate(() => (window as any).__narrativeStore.getState().worldItems.find((item: any) => item.id === 'wi_legacy').folderId)).toBe('folder_buildings');
});

test('folder collapse hides descendants without changing their stable parentId', async ({ page }) => {
  await installFixture(page);
  await page.getByTestId('world-folder-folder_places').locator('..').getByRole('button').first().click();
  await expect(page.getByTestId('world-folder-folder_buildings')).not.toBeVisible();
  const child = await page.evaluate(() => (window as any).__narrativeStore.getState().worldContainers.find((item: any) => item.id === 'folder_buildings'));
  expect(child.parentId).toBe('folder_places');
});
