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
    await expect(page.getByTestId('inspector')).toBeVisible();
    await expect(page.getByTestId('status-bar')).toBeVisible();
  });

  test('can navigate through activities and see sidebar sections', async ({ page }) => {
    // Workbench
    await page.getByTestId('activity-btn-workbench').click();
    await expect(page.getByTestId('sidebar-section-workbench-console')).toBeVisible();
    await expect(page.getByTestId('sidebar-section-workbench-prompts')).toBeVisible();

    // Characters
    await page.getByTestId('activity-btn-characters').click();
    await expect(page.getByTestId('sidebar-section-characters-list')).toBeVisible();
    await expect(page.getByTestId('sidebar-section-characters-candidates')).toBeVisible();
    
    // Timeline
    await page.getByTestId('activity-btn-timeline').click();
    await expect(page.getByTestId('sidebar-section-timeline-events')).toBeVisible();
    await expect(page.getByTestId('sidebar-section-timeline-branches')).toBeVisible();
  });

  test('command palette opens and navigates', async ({ page }) => {
    await page.getByTestId('global-search').click();
    await expect(page.getByTestId('command-palette')).toBeVisible();
    
    await page.keyboard.type('Writing');
    await page.getByText('Go to Writing Studio').click();
    
    await expect(page.getByTestId('writing-editor')).toBeVisible();
    await expect(page.getByTestId('command-palette')).not.toBeVisible();
  });

  test('can search for characters and navigate', async ({ page }) => {
    // Create a character first
    await page.getByTestId('activity-btn-characters').click();
    await page.getByTestId('new-character-btn').click();
    await page.getByTestId('character-name-input').fill('Searchable Hero');
    await page.getByTestId('character-background-input').fill('A hero to be searched.');
    await page.getByTestId('inspector-save').click();
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    // Now search for it
    await page.getByTestId('global-search').click();
    await expect(page.getByTestId('command-palette')).toBeVisible();
    
    await page.keyboard.type('Searchable');
    await page.getByTestId('command-palette').getByText('Searchable Hero').first().click();
    
    await expect(page.getByTestId('character-list')).toBeVisible();
    await expect(page.getByTestId('character-list')).toContainText('Searchable Hero');
    await expect(page.getByTestId('status-bar')).toContainText('Searchable Hero');

    // Test Tabs
    await page.getByTestId('char-tab-relationships').click();
    await expect(page.getByText('Network Connections')).toBeVisible();
    
    await page.getByTestId('char-tab-timeline').click();
    await expect(page.getByText('Character Timeline')).toBeVisible();

    await page.getByTestId('char-tab-profile').click();
    await expect(page.getByTestId('character-name-input')).toBeVisible();
  });

  test('can manage relationships', async ({ page }) => {
    await page.getByTestId('activity-btn-characters').click();
    
    // Create two characters
    await page.getByTestId('new-character-btn').click();
    await page.getByTestId('character-name-input').fill('Alice');
    await page.getByTestId('character-background-input').fill('Alice background');
    await page.getByTestId('inspector-save').click();
    
    await page.getByTestId('new-character-btn').click();
    await page.getByTestId('character-name-input').fill('Bob');
    await page.getByTestId('character-background-input').fill('Bob background');
    await page.getByTestId('inspector-save').click();

    // Go to Alice's relationships
    await page.getByText('Alice').first().click();
    await page.getByTestId('char-tab-relationships').click();
    
    // Add relationship to Bob
    await page.getByTestId('add-relationship-btn').click();
    await expect(page.getByTestId('relationship-card')).toContainText('Bob');
  });

  test('can interact with timeline events and drag reorder', async ({ page }) => {
    await page.getByTestId('activity-btn-timeline').click();
    
    // Add event
    await page.getByTestId('add-event-btn').click();
    await page.getByTestId('event-title-input').fill('Chronicle Start');
    await page.getByTestId('event-summary-input').fill('The beginning of time.');
    await page.getByTestId('inspector-save').click();
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    // Verify node exists
    const node = page.getByTestId(/timeline-node-event_/);
    await expect(node).toBeVisible();
    await expect(node).toContainText('Chronicle Start');

    // Simple drag test (checking branch change logic via store is better but smoke tests node existence after drop)
    await node.dragTo(page.getByTestId('timeline-branch-branch_main'));
    await expect(node).toBeVisible();
  });

  test('can use writing studio with sidebar and context panel', async ({ page }) => {
    // Create character and event for context panel
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

    // Go to writing
    await page.getByTestId('activity-btn-writing').click();
    await expect(page.getByTestId('writing-sidebar')).toBeVisible();
    await expect(page.getByTestId('context-panel')).toBeVisible();

    // Select scene
    await page.getByTestId('scene-item-scene_1').click();
    
    // Type in editor (use force click if needed)
    const editor = page.getByTestId('writing-editor');
    await editor.scrollIntoViewIfNeeded();
    await editor.click({ force: true });
    await page.keyboard.type('This is a test story.');
    await expect(page.getByText('Saved', { exact: true })).toBeVisible();

    // Check context panel
    await expect(page.getByTestId('context-panel')).toContainText('Alice');
    await expect(page.getByTestId('context-panel')).toContainText('Inciting Incident');

    // Click character in context panel should update status bar selection
    await page.getByTestId('context-insert-character').click();
    await expect(page.getByTestId('status-bar')).toContainText('Alice');
  });

  test('toolbar save action updates status bar', async ({ page }) => {
    await page.getByTestId('toolbar-save').click();
    await expect(page.getByTestId('status-bar')).toContainText('Saving');
    await expect(page.getByTestId('status-bar')).toContainText('Saved');
  });
});
