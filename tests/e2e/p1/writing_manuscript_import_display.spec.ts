/**
 * Writing Workspace — Import Display Tests
 *
 * Verifies that when a project has imported chapters/scenes in split-file
 * canonical storage, the Writing workspace displays them correctly:
 * - 10 imported Chinese chapters appear in numeric order (第一章…第十章)
 * - The blank starter chapter ("Chapter 1") is hidden after cleanup
 * - Scene content is non-empty for imported scenes
 *
 * Tests run against the web dev server (localhost:3000). Since getNodeRuntime()
 * returns null in a browser context, openProject() falls back to localStorage.
 * We pre-populate `narrative-ide-project` before the app boots.
 */

import { test, expect, Page } from '@playwright/test';

// ── Chinese chapter titles in correct numeric order ─────────────────────────

const CHAPTER_TITLES = [
  '第一章', '第二章', '第三章', '第四章', '第五章',
  '第六章', '第七章', '第八章', '第九章', '第十章',
];

// ── Minimal project fixture ──────────────────────────────────────────────────

/**
 * Build a project fixture with a blank starter chapter/scene + 10 imported
 * chapters in shuffled order. After cleanupImportedWritingArtifacts runs, the
 * result must be 10 chapters sorted 第一章…第十章 with the blank starter gone.
 */
function makeImportFixture() {
  // Chapters are provided in non-sequential order to exercise the sort.
  const shuffledIndices = [9, 0, 4, 7, 2, 5, 1, 8, 3, 6]; // index into CHAPTER_TITLES

  const importedChapters = shuffledIndices.map((i) => ({
    id: `chap_imp${String(i + 1).padStart(2, '0')}`,
    title: CHAPTER_TITLES[i],
    summary: `这是${CHAPTER_TITLES[i]}的概述。`,
    goal: '',
    notes: '',
    sceneIds: [`scene_imp${String(i + 1).padStart(2, '0')}`],
    orderIndex: i,
    status: 'draft',
  }));

  const importedScenes = shuffledIndices.map((i) => ({
    id: `scene_imp${String(i + 1).padStart(2, '0')}`,
    chapterId: `chap_imp${String(i + 1).padStart(2, '0')}`,
    title: '章节正文',
    summary: `${CHAPTER_TITLES[i]}场景概要`,
    content: `${CHAPTER_TITLES[i]}的正文内容，韩立踏上修仙之路，历经千辛万苦。`,
    orderIndex: 0,
    linkedCharacterIds: [],
    linkedEventIds: [],
    linkedWorldItemIds: [],
    status: 'draft',
  }));

  return {
    metadata: {
      schemaVersion: 4,
      projectId: 'proj_import_display_test',
      name: 'Import Display Test',
      rootPath: 'memory://import-display-test',
      storageMode: 'memory',
      locale: 'en',
      version: 4,
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-01T00:00:00.000Z',
      template: 'blank',
      capabilities: { import: true, rag: false, scripts: false },
      storageBackends: { canonical: 'project-folder-json', rag: 'project-folder-keyword-index' },
      futureBackends: [],
    },
    chapters: [
      // Blank starter — must match isBlankStarterChapter conditions exactly
      {
        id: 'chap_1',
        title: 'Chapter 1',
        summary: 'Starting chapter.',
        goal: '',
        notes: '',
        sceneIds: ['scene_1'],
        orderIndex: 0,
        status: 'draft',
      },
      ...importedChapters,
    ],
    scenes: [
      // Blank starter scene — content must be empty string
      {
        id: 'scene_1',
        chapterId: 'chap_1',
        title: 'Scene 1',
        summary: 'An empty starting scene.',
        content: '',
        orderIndex: 0,
        linkedCharacterIds: [],
        linkedEventIds: [],
        linkedWorldItemIds: [],
        status: 'draft',
      },
      ...importedScenes,
    ],
    // Remaining project fields are left absent; migrateProject fills defaults.
  };
}

// ── Setup helpers ────────────────────────────────────────────────────────────

async function injectProjectAndIpc(page: Page) {
  const fixture = makeImportFixture();

  await page.addInitScript(
    ({ project }) => {
      // Pre-load the project into localStorage so openProject() picks it up
      // when getNodeRuntime() returns null (no Node.js in browser context).
      localStorage.setItem('narrative-ide-project', JSON.stringify(project));
      localStorage.setItem('narrative-ide-last-path', 'memory://import-display-test');

      // Standard electron IPC mock used by all p1 specs
      const mockIpcRenderer = {
        invoke: async (channel: string) => {
          if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
          if (channel === 'settings:load-app') return {};
          return {};
        },
        on: () => {},
        removeAllListeners: () => {},
        send: () => {},
      };
      (window as any).require = (module: string) => {
        if (module === 'electron') return { ipcRenderer: mockIpcRenderer };
        throw new Error(`Module not found: ${module}`);
      };
    },
    { project: fixture }
  );
}

// ── Tests ────────────────────────────────────────────────────────────────────

test.describe('Writing workspace — imported chapter display', () => {
  test.beforeEach(async ({ page }) => {
    await injectProjectAndIpc(page);
    await page.goto('http://localhost:3000/writing/chapters');
    await expect(page.getByTestId('writing-chapters-sidebar')).toBeVisible();
  });

  test('imported chapters appear in numeric order 第一章…第十章', async ({ page }) => {
    const sidebar = page.getByTestId('writing-chapters-sidebar');
    // Each chapter button contains a div with the chapter title
    const titleDivs = sidebar.locator('[data-testid^="chapter-item-"] .text-sm.font-black');
    await expect(titleDivs).toHaveCount(10);

    const titles = await titleDivs.allTextContents();
    expect(titles).toEqual(CHAPTER_TITLES);
  });

  test('blank starter "Chapter 1" is not shown when imported chapters exist', async ({ page }) => {
    const sidebar = page.getByTestId('writing-chapters-sidebar');

    // The starter chapter button should not exist
    await expect(sidebar.getByTestId('chapter-item-chap_1')).not.toBeVisible();

    // No visible text matches "Chapter 1" in the sidebar chapter list area
    const allButtons = sidebar.locator('[data-testid^="chapter-item-"]');
    const buttonTexts = await allButtons.allTextContents();
    for (const text of buttonTexts) {
      expect(text.toLowerCase()).not.toMatch(/^chapter 1\b/);
    }
  });

  test('chapter card shows non-empty summary after clicking an imported chapter', async ({ page }) => {
    const sidebar = page.getByTestId('writing-chapters-sidebar');
    // Click 第一章 (the first chapter after sort)
    const firstChapterBtn = sidebar.locator('[data-testid^="chapter-item-"]').first();
    await firstChapterBtn.click();

    // The chapter editor panel should appear and the summary should be non-empty
    const summaryInput = page.getByTestId('chapter-summary-input');
    await expect(summaryInput).toBeVisible();
    const summaryValue = await summaryInput.inputValue();
    expect(summaryValue.trim().length).toBeGreaterThan(0);
  });
});

// ── Manuscript node view ──────────────────────────────────────────────────────

function makeManuscriptNodesFixture() {
  const chapters = CHAPTER_TITLES.map((title, i) => ({
    id: `chap_mn${String(i + 1).padStart(2, '0')}`,
    title,
    summary: `${title}概要`,
    goal: '', notes: '', sceneIds: [`scene_mn${String(i + 1).padStart(2, '0')}`],
    orderIndex: i, status: 'draft',
  }));
  const manuscriptNodes = chapters.flatMap((ch, i) => {
    const sceneId = `scene_mn${String(i + 1).padStart(2, '0')}`;
    const chNodeId = `mn_chap_mn${String(i + 1).padStart(2, '0')}`;
    const scNodeId = `mn_${sceneId}`;
    return [
      { id: chNodeId, title: ch.title, type: 'chapter_outline', parentId: null,
        orderIndex: i, linkedChapterId: ch.id, linkedSceneId: null,
        depth: 0, collapsed: false, wordCount: 50 },
      { id: scNodeId, title: '章节正文', type: 'scene_outline', parentId: chNodeId,
        orderIndex: 0, linkedChapterId: ch.id, linkedSceneId: sceneId,
        depth: 1, collapsed: false, wordCount: 50 },
    ];
  });
  return {
    metadata: {
      schemaVersion: 5, projectId: 'proj_mn_test', name: 'Manuscript Node Test',
      rootPath: 'memory://manuscript-node-test', storageMode: 'memory',
      locale: 'zh-CN', version: 5,
      createdAt: '2026-01-01T00:00:00.000Z', updatedAt: '2026-01-01T00:00:00.000Z',
      template: 'blank',
      capabilities: { import: true, rag: false, scripts: false },
      storageBackends: { canonical: 'project-folder-json', rag: 'project-folder-keyword-index' },
      futureBackends: [],
    },
    chapters,
    manuscriptNodes,
  };
}

async function injectManuscriptFixture(page: Page) {
  const fixture = makeManuscriptNodesFixture();
  await page.addInitScript(
    ({ project }) => {
      localStorage.setItem('narrative-ide-project', JSON.stringify(project));
      localStorage.setItem('narrative-ide-last-path', 'memory://manuscript-node-test');
      const mockIpcRenderer = {
        invoke: async (channel: string) => {
          if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
          if (channel === 'settings:load-app') return {};
          return {};
        },
        on: () => {}, removeAllListeners: () => {}, send: () => {},
      };
      (window as any).require = (module: string) => {
        if (module === 'electron') return { ipcRenderer: mockIpcRenderer };
        throw new Error(`Module not found: ${module}`);
      };
    },
    { project: fixture }
  );
}

test.describe('Writing workspace — manuscript node tree display', () => {
  test.beforeEach(async ({ page }) => {
    await injectManuscriptFixture(page);
    await page.goto('http://localhost:3000/writing/manuscript');
    await expect(page.getByTestId('manuscript-workspace')).toBeVisible();
  });

  test('manuscript workspace shows all 10 chapter nodes', async ({ page }) => {
    const workspace = page.getByTestId('manuscript-workspace');
    for (const title of CHAPTER_TITLES) {
      await expect(workspace.getByText(title, { exact: true })).toBeVisible();
    }
  });

  test('chapter nodes and scene nodes are present in the tree', async ({ page }) => {
    const chNode = page.getByTestId('manuscript-node-mn_chap_mn01');
    await expect(chNode).toBeVisible();
    const scNode = page.getByTestId('manuscript-node-mn_scene_mn01');
    await expect(scNode).toBeVisible();
  });
});

test.describe('Writing workspace — manuscript node content readability', () => {
  test('clicking a scene node shows non-empty content via loadManuscriptNodeContent', async ({ page }) => {
    const fixture = makeManuscriptNodesFixture();

    const fakeFiles: Record<string, string> = {};
    for (const node of fixture.manuscriptNodes) {
      if ((node as any).type === 'scene_outline') {
        const filePath = `memory://manuscript-node-test/writing/manuscript/${(node as any).id}.md`;
        fakeFiles[filePath] = `${(node as any).title}的正文内容，韩立踏上修仙之路。`;
      }
    }

    await page.addInitScript(
      ({ project, files }) => {
        localStorage.setItem('narrative-ide-project', JSON.stringify(project));
        localStorage.setItem('narrative-ide-last-path', 'memory://manuscript-node-test');
        const mockIpcRenderer = {
          invoke: async (channel: string) => {
            if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
            if (channel === 'settings:load-app') return {};
            return {};
          },
          on: () => {}, removeAllListeners: () => {}, send: () => {},
        };
        const fakeFsModule = {
          existsSync: (p: string) => p in (files as Record<string, string>),
          readFileSync: (p: string, _enc?: string) => (files as Record<string, string>)[p] ?? '',
          mkdirSync: () => {},
          writeFileSync: (p: string, content: string) => { (files as Record<string, string>)[p] = content; },
          readdirSync: () => [],
        };
        const fakePathModule = {
          join: (...parts: string[]) => parts.join('/').replace(/\/+/g, '/'),
        };
        (window as any).require = (module: string) => {
          if (module === 'electron') return { ipcRenderer: mockIpcRenderer };
          if (module === 'fs') return fakeFsModule;
          if (module === 'path') return fakePathModule;
          throw new Error(`Module not found: ${module}`);
        };
      },
      { project: fixture, files: fakeFiles }
    );

    await page.goto('http://localhost:3000/writing/manuscript');
    await expect(page.getByTestId('manuscript-workspace')).toBeVisible();

    await page.getByTestId('manuscript-node-mn_scene_mn01').click();
    await expect(page.getByTestId('manuscript-editor')).toBeVisible();

    const wordCountEl = page.getByTestId('manuscript-editor-wordcount');
    await expect(wordCountEl).not.toContainText('0 ');
  });
});
