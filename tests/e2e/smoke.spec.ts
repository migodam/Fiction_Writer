import { test, expect } from '@playwright/test';

test.describe('Narrative IDE Smoke Test', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('http://localhost:3000');
  });

  test('app layout is visible', async ({ page }) => {
    await expect(page.getByTestId('top-toolbar')).toBeVisible();
    await expect(page.getByTestId('activity-bar')).toBeVisible();
    await expect(page.getByTestId('sidebar')).toBeVisible();
    await expect(page.getByTestId('workspace')).toBeVisible();
    await expect(page.getByTestId('status-bar')).toBeVisible();
  });

  test('can navigate through activities and see sidebar sections', async ({ page }) => {
    await page.getByTestId('activity-btn-workbench').click();
    await expect(page.getByTestId('sidebar-section-workbench-inbox')).toBeVisible();
    await expect(page.getByTestId('sidebar-section-workbench-history')).toBeVisible();
    await expect(page.getByTestId('sidebar-section-workbench-imports')).toBeVisible();
    await expect(page.getByTestId('sidebar-section-workbench-runs')).toBeVisible();
    await expect(page.getByTestId('sidebar-section-workbench-prompts')).toBeVisible();

    await page.getByTestId('activity-btn-characters').click();
    await expect(page.getByTestId('sidebar-section-characters-list')).toBeVisible();
    await expect(page.getByTestId('sidebar-section-characters-candidates')).toBeVisible();

    await page.getByTestId('activity-btn-timeline').click();
    await expect(page.getByTestId('sidebar-section-timeline-overview')).toBeVisible();

    await page.getByTestId('activity-btn-world').click();
    await expect(page.getByTestId('world-container-list')).toBeVisible();

    await page.getByTestId('activity-btn-agents').click();
    await expect(page.getByTestId('agent-workspace')).toBeVisible();

    await page.getByTestId('activity-btn-publish').click();
    await expect(page.getByTestId('publish-workspace')).toBeVisible();
    await expect(page.getByTestId('sidebar-section-publish-video')).toBeVisible();

    await page.getByTestId('activity-btn-insights').click();
    await expect(page.getByTestId('insights-workspace')).toBeVisible();
  });

  test('workbench routes expose imports runs and prompts', async ({ page }) => {
    await page.getByTestId('activity-btn-workbench').click();

    await page.getByTestId('sidebar-section-workbench-imports').click();
    await expect(page.getByTestId('workbench-imports-list')).toBeVisible();

    await page.getByTestId('sidebar-section-workbench-runs').click();
    await expect(page.getByTestId('workbench-runs-list')).toBeVisible();

    await page.getByTestId('sidebar-section-workbench-prompts').click();
    await expect(page.getByTestId('workbench-prompts-list')).toBeVisible();
  });

  test('command palette opens and navigates', async ({ page }) => {
    await page.getByTestId('global-search').click();
    await expect(page.getByTestId('command-palette')).toBeVisible();

    await page.keyboard.type('Writing');
    await page.getByTestId('command-palette').getByRole('button', { name: /Writing Studio/i }).click();

    await expect(page.getByTestId('writing-editor')).toBeVisible();
    await expect(page.getByTestId('command-palette')).not.toBeVisible();
  });

  test('can search for characters and navigate', async ({ page }) => {
    await page.getByTestId('activity-btn-characters').click();
    await page.getByTestId('new-character-btn').click();
    await page.getByTestId('character-name-input').fill('Searchable Hero');
    await page.getByTestId('character-background-input').fill('A hero to be searched.');
    await page.getByTestId('inspector-save').click();
    await expect(page.getByText(/Saved|已保存/)).toBeVisible();

    await page.getByTestId('global-search').click();
    await expect(page.getByTestId('command-palette')).toBeVisible();

    await page.keyboard.type('Searchable');
    await page.getByTestId('command-palette').getByText('Searchable Hero').first().click();

    await expect(page.getByTestId('character-list')).toBeVisible();
    await expect(page.getByTestId('character-list')).toContainText('Searchable Hero');
    await expect(page.getByTestId('status-bar')).toContainText('Searchable Hero');

    await page.getByTestId('char-tab-relationships').click();
    await expect(page.getByTestId('add-relationship-btn')).toBeVisible();
    await page.getByTestId('add-relationship-btn').click();
    await expect(page.getByTestId('relationship-card').first()).toBeVisible();

    await page.getByTestId('char-tab-timeline').click();
    await expect(page.getByText(/Temporal Presence|时间存在/)).toBeVisible();

    await page.getByTestId('char-tab-profile').click();
    await expect(page.getByTestId('character-name-input')).toBeVisible();
  });

  test('can manage relationships', async ({ page }) => {
    await page.getByTestId('activity-btn-characters').click();

    await page.getByTestId('new-character-btn').click();
    await page.getByTestId('character-name-input').fill('Alice');
    await page.getByTestId('character-background-input').fill('Alice background');
    await page.getByTestId('inspector-save').click();

    await page.getByTestId('new-character-btn').click();
    await page.getByTestId('character-name-input').fill('Bob');
    await page.getByTestId('character-background-input').fill('Bob background');
    await page.getByTestId('inspector-save').click();

    await page.getByText('Alice').first().click();
    await page.getByTestId('char-tab-relationships').click();

    await page.getByTestId('add-relationship-btn').click();
    await expect(page.getByTestId('relationship-card')).toBeVisible();
  });

  test('can interact with timeline events and drag reorder', async ({ page }) => {
    await page.getByTestId('activity-btn-timeline').click();

    await page.getByTestId('add-event-btn').click();
    await page.getByTestId('event-title-input').fill('Chronicle Start');
    await page.getByTestId('event-summary-input').fill('The beginning of time.');
    await page.getByTestId('inspector-save').click();
    await expect(page.getByText(/Saved|已保存/)).toBeVisible();
    await expect(page.getByTestId('detail-modal')).not.toBeVisible();
    await expect(page.getByTestId('timeline-linear-inspector')).toContainText('Chronicle Start');
  });

  test('can use writing studio with sidebar and context panel', async ({ page }) => {
    await page.getByTestId('activity-btn-characters').click();
    await page.getByTestId('new-character-btn').click();
    await page.getByTestId('character-name-input').fill('Alice');
    await page.getByTestId('character-background-input').fill('Writing test char.');
    await page.getByTestId('inspector-save').click();

    await page.getByTestId('activity-btn-timeline').click();
    await page.getByTestId('add-event-btn').click();
    await page.getByTestId('event-title-input').fill('Inciting Incident');
    await page.getByTestId('event-summary-input').fill('Something happens.');
    await page.getByTestId('inspector-save').click();

    await page.getByTestId('activity-btn-writing').click();
    await expect(page.getByTestId('writing-sidebar')).toBeVisible();
    await expect(page.getByTestId('context-panel')).toBeVisible();

    await page.getByTestId('scene-item-scene_arrival').click();

    const editor = page.getByTestId('writing-editor');
    await editor.fill('This is a test story.');
    await expect(page.getByText(/Saved|已保存/)).toBeVisible();

    await expect(page.getByTestId('context-panel')).toContainText('Alice');
    await expect(page.getByTestId('context-panel')).toContainText('Inciting Incident');

    await page.getByTestId('context-insert-character').filter({ hasText: 'Alice' }).first().click();
    await expect(page.getByTestId('status-bar')).toContainText('Alice');
  });

  test('can use graph workspace with auto layout', async ({ page }) => {
    await page.getByTestId('activity-btn-graph').click();
    await expect(page.getByTestId('graph-canvas')).toBeVisible();

    await page.getByTestId('graph-add-node-btn').click();
    await page.getByTestId('graph-node-kind-input').selectOption('event_ref');
    await page.getByTestId('graph-node-label-input').fill('Graph Event');
    await page.getByTestId('graph-node-description-input').fill('Typed graph node.');
    await page.getByTestId('graph-node-save-btn').click();
    await expect(page.getByText('Node created', { exact: true })).toBeVisible();

    await page.getByTestId('graph-auto-layout-btn').click();
    await expect(page.getByText('Layout updated', { exact: true })).toBeVisible();

    await page.getByTestId('graph-fit-board-btn').click();
    await expect(page.getByTestId('graph-zoom-label')).toBeVisible();

    await page.getByTestId('graph-reset-layout-btn').click();
    await expect(page.getByText('Layout reset', { exact: true })).toBeVisible();
  });

  test('timeline renders explicit fork and merge markers', async ({ page }) => {
    await page.getByTestId('activity-btn-timeline').click();
    await expect(page.getByTestId('timeline-mainline')).toHaveCount(1);
    await expect(page.getByTestId('timeline-branch-branch_main')).toBeVisible();
    await expect(page.getByTestId('timeline-fork-branch_shadow')).toBeVisible();
    await expect(page.getByTestId('timeline-merge-branch_shadow')).toBeVisible();
    await expect(page.getByTestId('timeline-linear-inspector')).toBeVisible();
  });

  test('writing surfaces scripts and storyboards', async ({ page }) => {
    await page.getByTestId('activity-btn-writing').click();
    await page.getByTestId('sidebar-section-writing-chapters').click();
    await expect(page.getByTestId('chapter-editor')).toBeVisible();

    await page.getByTestId('add-chapter-btn').click();
    await page.getByTestId('chapter-title-input').fill('New Manual Chapter');
    await page.getByTestId('save-chapter-btn').click();
    await expect(page.getByText(/Saved|已保存/)).toBeVisible();

    await page.getByTestId('sidebar-section-writing-scenes').click();
    await page.getByTestId('add-scene-btn').click();
    await expect(page.getByTestId('writing-editor')).toBeVisible();

    await page.getByTestId('sidebar-section-writing-scripts').click();
    await expect(page.getByTestId('script-manuscript-panel')).toBeVisible();

    await page.getByTestId('sidebar-section-writing-storyboards').click();
    await expect(page.getByTestId('storyboard-panel')).toBeVisible();
  });

  test('publish surfaces video workflow packages', async ({ page }) => {
    await page.getByTestId('activity-btn-publish').click();
    await page.getByTestId('sidebar-section-publish-video').click();
    await expect(page.getByTestId('publish-video-workspace')).toBeVisible();
    await expect(page.getByTestId('video-package-video_pkg_ep1')).toBeVisible();
  });

  test('agent console captures instructions', async ({ page }) => {
    await page.getByTestId('activity-btn-agents').click();
    await page.getByTestId('agent-command-input').fill('Retrieve context for scene_arrival and prepare a summary.');
    await page.getByTestId('agent-command-submit').click();
    await expect(page.getByText('Agent instruction queued', { exact: true })).toBeVisible();
    await expect(page.getByTestId('agent-workspace')).toContainText('Retrieve context for scene_arrival');
  });

  test('can manage world model containers and items', async ({ page }) => {
    await page.getByTestId('activity-btn-world').click();
    await expect(page.getByTestId('world-container-list')).toBeVisible();

    await page.getByTestId('create-container-btn').click();
    await expect(page.getByTestId('world-container-list')).toContainText('New Container');

    await page.getByTestId('add-world-item-btn').click();
    await page.getByTestId('world-item-name-input').fill('Ancient Relic');
    await page.getByTestId('world-item-description-input').fill('A relic from the first age.');

    await page.getByTestId('dynamic-field-add-row').click();
    await page.getByTestId('dynamic-field-key-input').fill('Power Level');
    await page.getByTestId('dynamic-field-value-input').fill('Over 9000');

    await page.getByTestId('inspector-save').click();
    await expect(page.getByText(/Saved|已保存/)).toBeVisible();
    await expect(page.getByTestId('world-item-list')).toContainText('Ancient Relic');
  });

  test('can run simulation scenario', async ({ page }) => {
    await page.getByTestId('activity-btn-simulation').click();
    await expect(page.getByTestId('simulation-scenario-list')).toBeVisible();

    await page.getByText('Betrayal at Dawn').click();
    await page.getByTestId('run-simulation-btn').click();
    await expect(page.getByText('Simulation complete', { exact: true })).toBeVisible();
  });

  test('can run consistency audit and see issues', async ({ page }) => {
    await page.getByTestId('activity-btn-consistency').click();
    await expect(page.getByTestId('consistency-toolbar')).toBeVisible();

    await page.getByTestId('run-consistency-btn').click();
    await expect(page.getByText('Consistency check complete', { exact: true })).toBeVisible();
    await expect(page.getByTestId('consistency-issue-item')).toHaveCount(3);
  });

  test('can use beta reader simulation', async ({ page }) => {
    await page.getByTestId('activity-btn-beta').click();
    await expect(page.getByTestId('beta-reader-list')).toBeVisible();

    await page.getByTestId('beta-persona-beta_logician').click();
    await page.getByTestId('run-beta-reader-btn').click();
    await expect(page.getByText('Beta simulation complete', { exact: true })).toBeVisible();
    await expect(page.locator('span').filter({ hasText: 'Engagement' }).first()).toBeVisible();
  });

  test('toolbar save action updates status bar', async ({ page }) => {
    await page.getByTestId('toolbar-save').click();
    await expect(page.getByTestId('status-bar')).toContainText(/Saved|已保存/);
  });
});
