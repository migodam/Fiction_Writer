import { expect, test, type Page } from '@playwright/test';

interface StatusResult {
  status: string;
  progress: number;
  errors: string[];
  completed_chunks: number;
  total_chunks: number;
  current_step: string;
  current_tool?: string;
  current_window?: string;
  chapter_range?: string;
  orchestrator_phase?: string;
  last_activity_message?: string;
  active_api_calls?: number;
  elapsed_seconds?: number;
  idle_seconds?: number;
  cancel_requested?: boolean;
  converge_status?: string;
}

interface ActivityEntry {
  id: number;
  timestamp: string;
  level: string;
  phase: string;
  tool: string;
  window_id?: string;
  chapter_range?: string;
  prompt_label?: string;
  status: string;
  message: string;
  elapsed_ms?: number;
  active_api_calls?: number;
  error?: string;
}

async function injectIpcMock(
  page: Page,
  opts: {
    status: StatusResult;
    activityEntries?: ActivityEntry[];
  },
) {
  await page.addInitScript(
    ({ status, activityEntries }) => {
      const state = {
        status,
        activityEntries,
        statusCallCount: 0,
        consoleCallCount: 0,
      };
      (window as any).__mockW1ActivityState = state;

      const mockIpcRenderer = {
        invoke: async (channel: string) => {
          const s = (window as any).__mockW1ActivityState;
          if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
          if (channel === 'dialog:pick-files') return { canceled: false, paths: ['/tmp/test-novel.txt'] };
          if (channel === 'w1:start') return { session_id: 'mock-activity-session', status: 'started' };
          if (channel === 'w1:status') {
            s.statusCallCount += 1;
            return s.status;
          }
          if (channel === 'w1:console') {
            const first = s.consoleCallCount === 0;
            s.consoleCallCount += 1;
            return {
              entries: [],
              activity_entries: first ? s.activityEntries : [],
              paused: false,
              breakpoint_chunk: null,
            };
          }
          if (channel === 'w1:cancel') return { status: 'cancelled' };
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
    { status: opts.status, activityEntries: opts.activityEntries ?? [] },
  );
}

async function openImportModal(page: Page) {
  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();
  await expect(page.getByTestId('w1-file-picker-btn')).toBeVisible();
}

async function startImport(page: Page) {
  await page.getByTestId('w1-file-picker-btn').click();
  await expect(page.getByTestId('w1-current-activity-card')).toBeVisible({ timeout: 10_000 });
}

const WINDOW_ACTIVITY: ActivityEntry = {
  id: 1,
  timestamp: '2026-05-28T00:00:00Z',
  level: 'info',
  phase: 'extracting',
  tool: 'extract_window',
  window_id: 'pwin_003',
  chapter_range: 'Chapters 7-9',
  prompt_label: 'event',
  status: 'start',
  message: 'Running event prompt for pwin_003.',
  elapsed_ms: 4200,
  active_api_calls: 1,
};

test.describe('W1 import activity observability', () => {
  test('shows current AI activity before any chunk log exists', async ({ page }) => {
    await injectIpcMock(page, {
      status: {
        status: 'running',
        progress: 0.2,
        errors: [],
        completed_chunks: 0,
        total_chunks: 5,
        current_step: 'extracting',
        current_tool: 'extract_window',
        current_window: 'pwin_003',
        chapter_range: 'Chapters 7-9',
        orchestrator_phase: 'extracting',
        last_activity_message: 'Running event prompt for pwin_003.',
        active_api_calls: 1,
        elapsed_seconds: 12,
        idle_seconds: 3,
      },
      activityEntries: [WINDOW_ACTIVITY],
    });
    await openImportModal(page);
    await startImport(page);

    await expect(page.getByTestId('w1-current-activity-message')).toContainText('Running event prompt');
    await expect(page.getByTestId('w1-activity-phase')).toContainText('extracting');
    await expect(page.getByTestId('w1-activity-tool')).toContainText('extract_window');
    await expect(page.getByTestId('w1-activity-window')).toContainText('pwin_003');
    await expect(page.getByTestId('w1-activity-prompt')).toContainText('event');
    await expect(page.getByTestId('w1-activity-api-calls')).toContainText('1');
    await expect(page.getByTestId('console-activity-1')).toContainText('Running event prompt');
  });

  test('warns when activity is idle for 90 seconds or more', async ({ page }) => {
    await injectIpcMock(page, {
      status: {
        status: 'running',
        progress: 0.3,
        errors: [],
        completed_chunks: 0,
        total_chunks: 5,
        current_step: 'extracting',
        current_tool: 'extract_window',
        last_activity_message: 'Waiting for model response.',
        active_api_calls: 1,
        elapsed_seconds: 180,
        idle_seconds: 120,
      },
    });
    await openImportModal(page);
    await startImport(page);

    await expect(page.getByTestId('w1-idle-warning')).toBeVisible();
    await expect(page.getByTestId('w1-idle-warning')).toContainText('No new AI activity');
    await expect(page.getByTestId('w1-activity-idle')).toContainText('2m 0s');
  });

  test('renders budget exhausted as a red stop-loss state', async ({ page }) => {
    await injectIpcMock(page, {
      status: {
        status: 'running',
        progress: 0.4,
        errors: ['budget_exhausted: HTTP 402 insufficient balance'],
        completed_chunks: 1,
        total_chunks: 5,
        current_step: 'extracting',
        current_tool: 'extract_window',
        last_activity_message: 'Budget exhausted while running event prompt.',
        active_api_calls: 0,
        elapsed_seconds: 60,
        idle_seconds: 0,
        converge_status: 'budget_exhausted',
      },
      activityEntries: [{
        ...WINDOW_ACTIVITY,
        id: 2,
        level: 'error',
        status: 'fail',
        message: 'Budget exhausted while running event prompt.',
        error: 'HTTP 402 insufficient balance',
        active_api_calls: 0,
      }],
    });
    await openImportModal(page);
    await startImport(page);

    await expect(page.getByTestId('w1-current-activity-message')).toContainText('Budget exhausted');
    await expect(page.getByTestId('w1-current-activity-error')).toContainText('402');
    await expect(page.getByTestId('w1-error-item')).toContainText(/402|budget_exhausted/i);
    await expect(page.getByTestId('console-activity-2')).toContainText('Budget exhausted');
  });
});
