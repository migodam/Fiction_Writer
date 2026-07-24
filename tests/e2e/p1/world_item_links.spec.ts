import { expect, test } from '@playwright/test';

test('World item detail renders concrete event and scene links, including broken references', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState((state: any) => ({
      ...state,
      worldContainers: [{ id: 'nb_links', name: '世界模型', type: 'notebook', sortOrder: 0, parentId: null }],
      worldItems: [{ id: 'wi_links', folderId: 'nb_links', containerId: 'nb_links', type: 'location', name: '正门', description: '入口', attributes: [], linkedCharacterIds: [], linkedEventIds: ['event_missing'], linkedSceneIds: ['scene_missing'], mapMarkers: [], tagIds: [] }],
      timelineBranches: [{ id: 'branch_links', name: '主线', sortOrder: 0, mode: 'root' }],
      timelineEvents: [{ id: 'event_gate', title: '抵达正门', summary: '韩立抵达七玄门正门。', time: '第一日', branchId: 'branch_links', orderIndex: 0, locationIds: [], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: ['wi_links'], tags: [] }],
      chapters: [{ id: 'chapter_links', title: '第一章 入门', summary: '', goal: '', notes: '', sceneIds: ['scene_gate'], orderIndex: 0, status: 'draft' }],
      characters: [{ id: 'char_han', name: '韩立', summary: '', background: '', aliases: [], birthdayText: '', tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {} }],
      scenes: [{ id: 'scene_gate', chapterId: 'chapter_links', title: '正门外', summary: '韩立在正门外等待入门。', content: '', orderIndex: 0, povCharacterId: 'char_han', linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: ['wi_links'], status: 'draft' }],
    }));
  });
  await page.getByTestId('activity-btn-world').click();
  await page.getByTestId('world-folder-nb_links').click();
  await page.getByTestId('world-item-wi_links').click();

  await expect(page.getByTestId('world-link-event-event_gate')).toContainText('抵达正门');
  await expect(page.getByTestId('world-link-event-event_gate')).toContainText('第一日');
  await expect(page.getByTestId('world-link-event-event_gate')).toContainText('主线');
  await expect(page.getByTestId('world-link-scene-scene_gate')).toContainText('第一章 入门');
  await expect(page.getByTestId('world-link-scene-scene_gate')).toContainText('韩立');
  await expect(page.getByTestId('world-broken-event-event_missing')).toBeVisible();
  await expect(page.getByTestId('world-broken-scene-scene_missing')).toBeVisible();

  await page.getByTestId('world-link-event-event_gate').click();
  await expect(page).toHaveURL(/\/timeline\/timeline\?event=event_gate/);
});

test('View timeline uses worldItem and Timeline matches both locationIds and linkedWorldItemIds', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState((state: any) => ({
      ...state,
      worldContainers: [{ id: 'nb_filter', name: '世界模型', type: 'notebook', sortOrder: 0, parentId: null }],
      worldItems: [{ id: 'wi_filter', folderId: 'nb_filter', containerId: 'nb_filter', type: 'location', name: '山门', description: '', attributes: [], linkedCharacterIds: [], linkedEventIds: [], linkedSceneIds: [], mapMarkers: [], tagIds: [] }],
      timelineBranches: [{ id: 'branch_filter', name: '主线', sortOrder: 0, mode: 'root' }],
      timelineEvents: [
        { id: 'event_location', title: '地点关联', summary: '', branchId: 'branch_filter', orderIndex: 0, locationIds: ['wi_filter'], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: [], tags: [] },
        { id: 'event_world', title: '世界条目关联', summary: '', branchId: 'branch_filter', orderIndex: 1, locationIds: [], participantCharacterIds: [], linkedSceneIds: [], linkedWorldItemIds: ['wi_filter'], tags: [] },
      ],
    }));
  });
  await page.getByTestId('activity-btn-world').click();
  await page.getByTestId('world-folder-nb_filter').click();
  await page.getByTestId('world-item-wi_filter').click();
  await page.getByTestId('open-world-timeline-btn').click();
  await expect(page).toHaveURL(/worldItem=wi_filter/);
  await expect(page.getByTestId('timeline-event-node-event_location')).toBeVisible();
  await expect(page.getByTestId('timeline-event-node-event_world')).toBeVisible();
});
