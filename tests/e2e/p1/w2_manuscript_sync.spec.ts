import { test, expect, Page } from '@playwright/test';

type W2StatusResult = {
  status: string;
  progress: number;
  errors: string[];
  proposals_count: number;
};

async function injectW2IpcMock(
  page: Page,
  opts: {
    startResult?: { session_id: string; status: string; error?: string };
    statusResults?: W2StatusResult[];
  } = {},
) {
  const startResult = opts.startResult ?? { session_id: 'w2-session-001', status: 'started' };
  const statusResults = opts.statusResults ?? [
    { status: 'running', progress: 0.35, errors: [], proposals_count: 0 },
    { status: 'done', progress: 1, errors: [], proposals_count: 2 },
  ];

  await page.addInitScript(
    ({ startResult, statusResults }) => {
      (window as any).__w2StatusCallCount = 0;

      const mockIpcRenderer = {
        invoke: async (channel: string, payload: unknown) => {
          if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
          if (channel === 'w2:start') {
            (window as any).__lastW2StartPayload = payload;
            return startResult;
          }
          if (channel === 'w2:status') {
            (window as any).__lastW2StatusPayload = payload;
            const index = Math.min((window as any).__w2StatusCallCount, statusResults.length - 1);
            (window as any).__w2StatusCallCount += 1;
            return statusResults[index];
          }
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
    { startResult, statusResults },
  );
}

async function openWritingChapters(page: Page) {
  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-writing').click();
  await page.getByTestId('sidebar-section-writing-chapters').click();
  await expect(page.getByTestId('chapter-editor')).toBeVisible();
}

test.describe('W2 Manuscript Sync UI', () => {
  test('starts from Writing Chapters, polls status, and links results to Workbench', async ({ page }) => {
    await injectW2IpcMock(page);
    await openWritingChapters(page);

    await page.getByTestId('w2-sync-chapter-btn').click();

    await expect(page.getByTestId('w2-status-card')).toBeVisible();
    await expect(page.getByTestId('w2-status-label')).toContainText(/Scanning|proposal/i, { timeout: 8000 });
    await expect(page.getByTestId('w2-status-label')).toContainText('2 proposal(s) sent to Workbench', { timeout: 10000 });
    await expect(page.getByTestId('w2-open-workbench-btn')).toBeVisible();

    const startPayload = await page.evaluate(() => (window as any).__lastW2StartPayload as Record<string, unknown>);
    expect(startPayload.mode).toBe('single_chapter');
    expect(startPayload.target_chapter_id).toBeTruthy();
    expect(Object.keys(startPayload)).toContain('api_key');
    expect(Object.keys(startPayload)).toContain('model');
    expect(Object.keys(startPayload)).toContain('endpoint');

    await page.getByTestId('w2-open-workbench-btn').click();
    await expect(page).toHaveURL(/\/workbench\/inbox/);
    await expect(page.getByTestId('workbench-inbox-list')).toBeVisible();
  });

  test('shows an actionable error when W2 fails', async ({ page }) => {
    await injectW2IpcMock(page, {
      statusResults: [
        { status: 'error', progress: 0.2, errors: ['entity extraction failed: invalid api key'], proposals_count: 0 },
      ],
    });
    await openWritingChapters(page);

    await page.getByTestId('w2-sync-chapter-btn').click();

    await expect(page.getByTestId('w2-error-msg')).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId('w2-error-msg')).toContainText(/invalid api key/i);
  });
});
