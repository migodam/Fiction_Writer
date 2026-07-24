import { expect, test } from '@playwright/test';

test('character tags and injected World folders retain their visible hierarchy', async ({ page }) => {
  await page.goto('http://localhost:3000/characters/tags');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState((state: any) => ({
      ...state,
      characterTags: [
        { id: 'tag_root', name: 'Root', color: '#f59e0b', description: '', characterIds: [], parentTagId: null, sortOrder: 0 },
        { id: 'tag_child', name: 'Child', color: '#38bdf8', description: '', characterIds: [], parentTagId: 'tag_root', sortOrder: 0 },
      ],
    }));
  });

  await expect(page.getByTestId('character-tag-row-tag_root')).toBeVisible();
  await expect(page.getByTestId('character-tag-row-tag_child')).toBeVisible();

  await page.goto('http://localhost:3000/world');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState((state: any) => ({
      ...state,
      worldContainers: [
        { id: 'folder_imported_root', name: 'Imported World', type: 'notebook', sortOrder: 100 },
        { id: 'folder_imported_child', name: 'Places', type: 'notebook', parentId: 'folder_imported_root', sortOrder: 101 },
      ],
    }));
  });

  await expect(page.getByTestId('world-container-folder_imported_root')).toBeVisible();
  await page.getByTestId('world-container-folder_imported_root').click();
  await expect(page.getByTestId('world-folder-folder_imported_root')).toHaveText('Imported World');
  await expect(page.getByTestId('world-folder-folder_imported_child')).toBeVisible();
  await expect(page.getByTestId('world-folder-folder_imported_child')).toHaveText('Places');
  await expect(page.getByTestId('world-category-tree')).toHaveCount(0);
});
