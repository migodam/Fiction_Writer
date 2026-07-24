import { expect, test } from '@playwright/test';

const character = {
  id: 'w1-character', name: 'Aster', summary: 'Lead', background: 'A careful archivist.', aliases: [], birthdayText: '',
  tagIds: [], organizationIds: [], linkedSceneIds: [], linkedEventIds: [], linkedWorldItemIds: [], statusFlags: {},
};

test('character evidence rows persist through the character draft save', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate((fixture) => (window as any).__narrativeStore.setState((state: any) => ({ ...state, characters: [...state.characters, fixture] })), character);
  await page.evaluate(() => { window.history.pushState({}, '', '/characters/profile/w1-character'); window.dispatchEvent(new PopStateEvent('popstate')); });
  await page.getByTestId('character-custom-attribute-add').click();
  const attributeId = await page.locator('[data-testid^="character-custom-attribute-label-"]').evaluate((node) => node.getAttribute('data-testid')!.replace('character-custom-attribute-label-', ''));
  await page.getByTestId(`character-custom-attribute-label-${attributeId}`).fill('Role');
  await page.getByTestId(`character-custom-attribute-value-${attributeId}`).fill('Archivist');
  await page.getByTestId('character-experience-add').click();
  const experienceId = await page.locator('[data-testid^="character-experience-chapter-"]').evaluate((node) => node.getAttribute('data-testid')!.replace('character-experience-chapter-', ''));
  await page.getByTestId(`character-experience-chapter-${experienceId}`).fill('2');
  await page.getByTestId(`character-experience-fact-${experienceId}`).fill('Found the sealed ledger');
  await page.getByTestId('inspector-save').click();
  const saved = await page.evaluate(() => (window as any).__narrativeStore.getState().characters.find((entry: any) => entry.id === 'w1-character'));
  expect(saved.customAttributes).toEqual([{ id: attributeId, label: 'Role', value: 'Archivist' }]);
  expect(saved.experience[0]).toMatchObject({ id: experienceId, chapter: '2', fact: 'Found the sealed ledger' });
});

test('manuscript outline exposes hierarchy and save state', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => (window as any).__narrativeStore.setState({ manuscriptNodes: [
    { id: 'chapter-outline', title: 'Chapter One', type: 'chapter_outline', parentId: null, orderIndex: 0, linkedChapterId: 'ch-1', linkedSceneId: null, depth: 0, collapsed: false, wordCount: 0 },
    { id: 'scene-outline', title: 'Arrival', type: 'scene_outline', parentId: 'chapter-outline', orderIndex: 0, linkedChapterId: 'ch-1', linkedSceneId: 'sc-1', depth: 1, collapsed: false, wordCount: 0 },
  ] }));
  await page.evaluate(() => { window.history.pushState({}, '', '/writing/manuscript'); window.dispatchEvent(new PopStateEvent('popstate')); });
  await expect(page.getByTestId('manuscript-node-chapter-outline')).toBeVisible();
  await expect(page.getByTestId('manuscript-node-scene-outline')).toBeVisible();
  await page.getByTestId('manuscript-node-chapter-outline').click();
  await expect(page.getByTestId('manuscript-save-state')).toHaveText('saved');
});

test('import run entry projects status, budget, and recovery without a live call', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => (window as any).__narrativeStore.setState({
    w1Status: 'error', w1CurrentStep: 'review', w1Errors: ['budget_exhausted'],
    w1TokenLedger: { actual_input_tokens: 40, actual_output_tokens: 60, actual_total_tokens: 100, api_call_count: 1, estimated_input_tokens: 0 },
  }));
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();
  await expect(page.getByTestId('w1-import-entry')).toBeVisible();
  await expect(page.getByTestId('w1-import-stage')).toContainText('review');
  await expect(page.getByTestId('w1-import-budget')).toContainText('100');
  await expect(page.getByTestId('w1-recovery-card')).toBeVisible();
});

test('world folders are projected once from stable parent IDs', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => (window as any).__narrativeStore.setState((state: any) => ({ ...state, worldContainers: [
    ...state.worldContainers,
    { id: 'notebook-root', name: 'Atlas', type: 'notebook', sortOrder: 90, parentId: null },
    { id: 'notebook-folder', name: 'Cities', type: 'notebook', sortOrder: 91, parentId: 'notebook-root' },
  ] })));
  await page.getByTestId('activity-btn-world').click();
  await expect(page.getByTestId('world-container-notebook-root')).toHaveCount(1);
  await page.getByTestId('world-container-notebook-root').click();
  await expect(page.getByTestId('world-folder-notebook-folder')).toHaveCount(1);
  await expect(page.getByTestId('world-folder-notebook-folder')).toHaveText('Cities');
});
