import { expect, test } from '@playwright/test';

const storyGapFixture = {
  metadata: {
    schemaVersion: 5,
    projectId: 'proj_backlog_story_gaps',
    name: 'Backlog Story Gaps',
    rootPath: 'memory://backlog-story-gaps',
    storageMode: 'memory',
    locale: 'en',
    version: 1,
    createdAt: '2026-07-11T00:00:00.000Z',
    updatedAt: '2026-07-11T00:00:00.000Z',
    template: 'blank',
  },
  chapters: [{ id: 'chap_gap', title: 'Unresolved Chapter', summary: '', goal: '', notes: '', sceneIds: [], orderIndex: 0, status: 'draft' }],
  scenes: [{ id: 'scene_gap', chapterId: 'chap_gap', title: 'Brief scene', summary: '', content: 'Too short.', orderIndex: 0, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft' }],
  characters: [],
};

test.describe('Backlog story gaps', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript((project) => {
      localStorage.setItem('narrative-ide-project', JSON.stringify(project));
      localStorage.setItem('narrative-ide-last-path', project.metadata.rootPath);
    }, storyGapFixture);
    await page.goto('http://localhost:3000/workbench/tasks');
    await expect(page.getByTestId('sidebar-section-workbench-tasks')).toBeVisible();
  });

  test('story gaps tab is reachable from the Backlog workspace and shows refresh', async ({ page }) => {
    await page.getByTestId('backlog-story-gaps-tab').click();

    await expect(page.getByTestId('backlog-refresh-btn')).toBeVisible();
  });

  test('refresh preserves the computed gaps or the empty state', async ({ page }) => {
    await page.getByTestId('backlog-story-gaps-tab').click();
    await page.getByTestId('backlog-refresh-btn').click();

    const noGaps = page.getByTestId('backlog-no-gaps');
    const gapItems = page.locator('[data-testid^="backlog-gap-item-"]');

    await expect(noGaps.or(gapItems.first())).toBeVisible();
  });
});
