import { test, expect } from '@playwright/test';

const chapterPreviewFixture = {
  metadata: {
    schemaVersion: 5,
    projectId: 'proj_chapter_preview',
    name: 'Chapter Preview Fixture',
    rootPath: 'memory://chapter-preview',
    storageMode: 'memory',
    locale: 'en',
    version: 1,
    createdAt: '2026-07-11T00:00:00.000Z',
    updatedAt: '2026-07-11T00:00:00.000Z',
    template: 'blank',
  },
  chapters: [{ id: 'chap_preview', title: 'Previewable Chapter', summary: 'A deterministic preview.', goal: '', notes: '', sceneIds: ['scene_preview'], orderIndex: 0, status: 'draft' }],
  scenes: [{ id: 'scene_preview', chapterId: 'chap_preview', title: 'Previewable Scene', summary: 'A scene used only by this preview test.', content: 'A deterministic chapter preview has enough words to render its summary and reading statistics.', orderIndex: 0, povCharacterId: null, linkedCharacterIds: [], linkedEventIds: [], linkedWorldItemIds: [], status: 'draft' }],
};

test.describe('Chapter preview modal', () => {
    test.beforeEach(async ({ page }) => {
        await page.addInitScript((project) => {
            localStorage.setItem('narrative-ide-project', JSON.stringify(project));
            localStorage.setItem('narrative-ide-last-path', project.metadata.rootPath);
        }, chapterPreviewFixture);
        await page.goto('http://localhost:3000/writing/chapters');
    });

    test('chapter preview modal opens and closes', async ({ page }) => {
        const previewBtn = page.locator('[data-testid^="chapter-preview-btn-"]').first();
        await previewBtn.click();

        await expect(page.getByTestId('chapter-preview-modal')).toBeVisible();
        await expect(page.getByTestId('chapter-preview-stats')).toBeVisible();
        await expect(page.getByTestId('chapter-preview-modal')).toContainText('Previewable Chapter');
        await expect(page.getByTestId('chapter-preview-scene-scene_preview')).toBeVisible();

        await page.getByTestId('chapter-preview-close-btn').click();

        await expect(page.getByTestId('chapter-preview-modal')).not.toBeVisible();
    });
});
