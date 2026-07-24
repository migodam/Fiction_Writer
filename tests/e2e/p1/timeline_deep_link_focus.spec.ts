import { expect, test } from '@playwright/test';

test('World event deep link focuses the concrete event without reclaiming manual pan', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState((state: any) => ({
      ...state,
      worldContainers: [{ id: 'nb_focus', name: '世界模型', type: 'notebook', sortOrder: 0, parentId: null }],
      worldItems: [{
        id: 'world_focus', folderId: 'nb_focus', containerId: 'nb_focus', type: 'location', name: '山门', description: '',
        attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], tagIds: [],
      }],
      timelineBranches: [
        { id: 'branch_main', name: '主线', sortOrder: 0, mode: 'root' },
        { id: 'branch_hidden', name: '暗线', sortOrder: 1, mode: 'independent', geometry: { laneOffset: 320, bend: 0.35, thickness: 1 } },
      ],
      timelineEvents: [
        { id: 'event_main', title: '主线开端', summary: '', time: '第一日', branchId: 'branch_main', orderIndex: 0, locationIds: [], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: [], tags: [] },
        { id: 'event_bridge', title: '抵达山门', summary: '具体事件', time: '第三日', branchId: 'branch_hidden', orderIndex: 0, position: { x: 1780, y: 500 }, locationIds: ['world_focus'], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: ['world_focus'], tags: [] },
      ],
    }));
  });

  await page.getByTestId('activity-btn-world').click();
  await page.getByTestId('world-folder-nb_focus').click();
  await page.getByTestId('world-item-world_focus').click();
  await page.getByTestId('world-link-event-event_bridge').click();

  await expect(page).toHaveURL(/\/timeline\/timeline\?event=event_bridge/);
  await expect(page.getByTestId('timeline-focus-banner')).toContainText('抵达山门');
  await expect(page.getByTestId('timeline-focus-banner')).toContainText('第三日');
  await expect(page.getByTestId('timeline-focus-banner')).toContainText('暗线');
  await expect(page.getByTestId('timeline-event-focus-ring-event_bridge')).toBeVisible();

  await expect.poll(() => page.evaluate(() => (window as any).__narrativeStore.getState().selectedEntity)).toEqual({
    type: 'timeline_event',
    id: 'event_bridge',
  });

  const eventBox = await page.getByTestId('timeline-event-node-event_bridge').boundingBox();
  const canvasBox = await page.getByTestId('timeline-canvas').boundingBox();
  expect(eventBox).not.toBeNull();
  expect(canvasBox).not.toBeNull();
  if (!eventBox || !canvasBox) throw new Error('Timeline geometry was unavailable');
  expect(eventBox.x + eventBox.width / 2).toBeGreaterThan(canvasBox.x + canvasBox.width * 0.3);
  expect(eventBox.x + eventBox.width / 2).toBeLessThan(canvasBox.x + canvasBox.width * 0.7);
  expect(eventBox.y + eventBox.height / 2).toBeGreaterThan(canvasBox.y + canvasBox.height * 0.3);
  expect(eventBox.y + eventBox.height / 2).toBeLessThan(canvasBox.y + canvasBox.height * 0.7);

  const canvas = page.getByTestId('timeline-svg');
  const box = await canvas.boundingBox();
  if (!box) throw new Error('Timeline SVG was unavailable');
  const beforePan = await page.locator('#events').evaluate((node) => node.parentElement?.getAttribute('transform'));
  await page.mouse.move(box.x + 80, box.y + 80);
  await page.mouse.down();
  await page.mouse.move(box.x + 160, box.y + 140, { steps: 6 });
  await page.mouse.up();
  await page.waitForTimeout(150);
  const afterPan = await page.locator('#events').evaluate((node) => node.parentElement?.getAttribute('transform'));
  expect(afterPan).not.toBe(beforePan);

  await page.getByTestId('timeline-clear-event-focus').click();
  await expect(page.getByTestId('timeline-focus-banner')).toHaveCount(0);
  await expect(page).not.toHaveURL(/event=event_bridge/);
});

test('World item filter remains explicit and shows both canonical world reference fields', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState((state: any) => ({
      ...state,
      worldContainers: [{ id: 'nb_filter_focus', name: '世界模型', type: 'notebook', sortOrder: 0, parentId: null }],
      worldItems: [{ id: 'world_filter_focus', folderId: 'nb_filter_focus', containerId: 'nb_filter_focus', type: 'location', name: '外门', description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], tagIds: [] }],
      timelineBranches: [{ id: 'branch_filter_focus', name: '主线', sortOrder: 0, mode: 'root' }],
      timelineEvents: [
        { id: 'event_location_focus', title: '地点引用', summary: '', branchId: 'branch_filter_focus', orderIndex: 0, locationIds: ['world_filter_focus'], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: [], tags: [] },
        { id: 'event_world_focus', title: '世界引用', summary: '', branchId: 'branch_filter_focus', orderIndex: 1, locationIds: [], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: ['world_filter_focus'], tags: [] },
      ],
    }));
  });

  await page.getByTestId('activity-btn-world').click();
  await page.getByTestId('world-folder-nb_filter_focus').click();
  await page.getByTestId('world-item-world_filter_focus').click();
  await page.getByTestId('open-world-timeline-btn').click();

  await expect(page.getByTestId('timeline-filter-state')).toContainText('外门');
  await expect(page.getByTestId('timeline-event-node-event_location_focus')).toBeVisible();
  await expect(page.getByTestId('timeline-event-node-event_world_focus')).toBeVisible();
});
