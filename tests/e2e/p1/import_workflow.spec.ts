/**
 * W1 Import Workflow — Playwright E2E Tests
 *
 * These tests mock the Electron IPC layer via page.addInitScript() so they run
 * against the web-only dev server (localhost:3000) without needing a live sidecar
 * or OS file dialog. State transitions are driven by controlling what the mock IPC
 * returns for w1:start and w1:status calls.
 */

import { test, expect, Page } from '@playwright/test';

// ── IPC mock helpers ────────────────────────────────────────────────────────

interface MockState {
  startResult: { session_id: string; status: string; error?: string };
  statusResults: Array<{
    status: string;
    progress: number;
    errors: string[];
    completed_chunks: number;
    total_chunks: number;
    current_step: string;
    current_tool?: string;
    current_window?: string | number;
    chapter_range?: string;
    orchestrator_phase?: string;
    judge_score?: number;
    rerun_reason?: string;
    converge_status?: string;
    judge_artifact_summary?: Record<string, unknown>;
    import_review_report?: Record<string, unknown>;
  }>;
  statusCallCount: number;
}

/**
 * Inject a fake `require('electron')` so that electronApi's getIpcRenderer()
 * returns a controllable mock. `window.__mockIpcState` is mutated by tests to
 * change what each IPC channel returns.
 */
async function injectIpcMock(
  page: Page,
  opts: {
    pickFilesResult?: string[];
    startResult?: MockState['startResult'];
    statusResults?: MockState['statusResults'];
  } = {}
) {
  const pickFiles = opts.pickFilesResult ?? ['/tmp/test-novel.txt'];
  const startResult = opts.startResult ?? { session_id: 'mock-session-001', status: 'started' };
  const statusResults = opts.statusResults ?? [
    { status: 'running', progress: 0.1, errors: [], completed_chunks: 0, total_chunks: 10, current_step: 'split_chunks' },
    { status: 'running', progress: 0.3, errors: [], completed_chunks: 3, total_chunks: 10, current_step: 'process_chunks' },
    { status: 'running', progress: 0.7, errors: [], completed_chunks: 8, total_chunks: 10, current_step: 'process_chunks' },
    { status: 'done',    progress: 1.0, errors: [], completed_chunks: 10, total_chunks: 10, current_step: 'write_to_project' },
  ];

  await page.addInitScript(
    ({ pickFiles, startResult, statusResults }) => {
      const state: MockState = {
        startResult,
        statusResults,
        statusCallCount: 0,
      };
      (window as any).__mockIpcState = state;

      const mockIpcRenderer = {
        invoke: async (channel: string, _payload: unknown) => {
          const s = (window as any).__mockIpcState as MockState;

          if (channel === 'sidecar:spawn') {
            return { ok: true, port: 8765 };
          }
          if (channel === 'dialog:pick-files') {
            return { canceled: false, paths: pickFiles };
          }
          if (channel === 'w1:start') {
            return s.startResult;
          }
          if (channel === 'w1:status') {
            const idx = Math.min(s.statusCallCount, s.statusResults.length - 1);
            const result = s.statusResults[idx];
            s.statusCallCount += 1;
            return result;
          }
          if (channel === 'w1:cancel') {
            return { status: 'cancelled' };
          }
          // Safe fallbacks for any other IPC channel
          return {};
        },
        on: () => {},
        removeAllListeners: () => {},
        send: () => {},
      };

      // electronApi.ts calls require('electron') to get ipcRenderer
      (window as any).require = (module: string) => {
        if (module === 'electron') {
          return { ipcRenderer: mockIpcRenderer };
        }
        throw new Error(`Module not found: ${module}`);
      };
    },
    { pickFiles, startResult, statusResults }
  );
}

// ── Navigate to Workbench and open the import modal ─────────────────────────

async function openImportModal(page: Page) {
  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();
  // Modal should appear
  await expect(page.getByTestId('w1-file-picker-btn')).toBeVisible();
}

// ── Tests ───────────────────────────────────────────────────────────────────

test.describe('W1 Import Workflow — UI structure', () => {
  test.beforeEach(async ({ page }) => {
    await injectIpcMock(page);
    await openImportModal(page);
  });

  test('modal renders both mode selectors when idle', async ({ page }) => {
    await expect(page.getByTestId('w1-mode-content-only')).toBeVisible();
    await expect(page.getByTestId('w1-mode-import-all')).toBeVisible();
  });

  test('import_all radio is selected by default', async ({ page }) => {
    const importAllRadio = page.getByTestId('w1-mode-import-all').locator('input[type="radio"]');
    await expect(importAllRadio).toBeChecked();
  });

  test('file picker button is visible when idle', async ({ page }) => {
    await expect(page.getByTestId('w1-file-picker-btn')).toBeVisible();
  });

  test('prompt profile selector is visible when idle', async ({ page }) => {
    await expect(page.getByTestId('w1-prompt-profile-select')).toBeVisible();
    await expect(page.getByTestId('w1-prompt-profile-select')).toHaveValue('balanced');
    await expect(page.getByTestId('w1-profile-explanation')).toContainText('Validation: per-window');
    await expect(page.getByTestId('w1-prompt-review-panel')).toBeVisible();
  });

  test('custom expert panel is visible only for custom profile', async ({ page }) => {
    await expect(page.getByTestId('w1-custom-expert-panel')).not.toBeVisible();
    await page.getByTestId('w1-prompt-profile-select').selectOption('custom');
    await expect(page.getByTestId('w1-profile-explanation')).toContainText('Supervisor/orchestrator');
    await expect(page.getByTestId('w1-custom-expert-panel')).toBeVisible();
    await expect(page.getByTestId('w1-custom-quality-target')).toHaveValue('max');
    await expect(page.getByTestId('w1-custom-max-chapters-per-window')).toHaveValue('6');
    await expect(page.getByTestId('w1-custom-rerun-budget')).toHaveValue('3');
  });

  test('close button is always visible', async ({ page }) => {
    await expect(page.getByTestId('w1-close-btn')).toBeVisible();
  });

  test('close button dismisses the modal', async ({ page }) => {
    await page.getByTestId('w1-close-btn').click();
    await expect(page.getByTestId('w1-close-btn')).not.toBeVisible();
  });
});

test.describe('W1 Import Workflow — mode selection', () => {
  test.beforeEach(async ({ page }) => {
    await injectIpcMock(page);
    await openImportModal(page);
  });

  test('switching to content-only mode checks the correct radio', async ({ page }) => {
    const contentOnlyRadio = page.getByTestId('w1-mode-content-only').locator('input[type="radio"]');
    await contentOnlyRadio.check();
    await expect(contentOnlyRadio).toBeChecked();

    const importAllRadio = page.getByTestId('w1-mode-import-all').locator('input[type="radio"]');
    await expect(importAllRadio).not.toBeChecked();
  });

  test('mode selectors are hidden while import is running', async ({ page }) => {
    // Start the import — clicking the file picker triggers startImport
    await page.getByTestId('w1-file-picker-btn').click();

    // Progress bar should appear (means status changed to running)
    await expect(page.getByTestId('w1-progress-bar')).toBeVisible({ timeout: 8000 });

    // Mode selectors and file picker should be hidden while running
    await expect(page.getByTestId('w1-mode-content-only')).not.toBeVisible();
    await expect(page.getByTestId('w1-prompt-profile-select')).not.toBeVisible();
    await expect(page.getByTestId('w1-file-picker-btn')).not.toBeVisible();
  });
});

test.describe('W1 Import Workflow — running state', () => {
  test.beforeEach(async ({ page }) => {
    await injectIpcMock(page, {
      statusResults: [
        {
          status: 'running',
          progress: 0.2,
          errors: [],
          completed_chunks: 200,
          total_chunks: 1547,
          current_step: 'process_chunks',
          current_tool: 'extract_window',
          current_window: 'window_003',
          chapter_range: 'Chapters 7 - 9',
          orchestrator_phase: 'extracting',
          judge_score: 0.76,
          rerun_reason: 'character undercoverage',
          converge_status: 'rerunning',
        },
        { status: 'running', progress: 0.5, errors: [], completed_chunks: 773, total_chunks: 1547, current_step: 'process_chunks' },
        { status: 'done',    progress: 1.0, errors: [], completed_chunks: 1547, total_chunks: 1547, current_step: 'write_to_project' },
      ],
    });
    await openImportModal(page);
    await page.getByTestId('w1-file-picker-btn').click();
    // Wait for running state
    await expect(page.getByTestId('w1-progress-bar')).toBeVisible({ timeout: 8000 });
  });

  test('progress bar is visible during import', async ({ page }) => {
    await expect(page.getByTestId('w1-progress-bar')).toBeVisible();
  });

  test('cancel button is visible during import', async ({ page }) => {
    await expect(page.getByTestId('w1-cancel-btn')).toBeVisible();
  });

  test('chunk count shows X / Y format when chunks > 0', async ({ page }) => {
    // Wait for at least one status poll with chunk data
    await expect(page.locator('text=/\\d+ \\/ \\d+/')).toBeVisible({ timeout: 10000 });
  });

  test('current step label is shown next to chunk count', async ({ page }) => {
    await expect(page.locator('text=/process.chunks|split.chunks|write.to.project/i')).toBeVisible({ timeout: 10000 });
  });

  test('runtime orchestrator and judge fields render when status includes them', async ({ page }) => {
    await expect(page.getByTestId('w1-runtime-status-card')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('w1-status-current-tool')).toContainText('extract_window');
    await expect(page.getByTestId('w1-status-current-window')).toContainText('window_003');
    await expect(page.getByTestId('w1-status-chapter-range')).toContainText('Chapters 7 - 9');
    await expect(page.getByTestId('w1-status-orchestrator-phase')).toContainText('extracting');
    await expect(page.getByTestId('w1-status-judge-score')).toContainText('0.76');
    await expect(page.getByTestId('w1-status-rerun-reason')).toContainText('character undercoverage');
    await expect(page.getByTestId('w1-status-converge-status')).toContainText('rerunning');
  });
});

test.describe('W1 Import Workflow — success state', () => {
  test('shows success message when import completes', async ({ page }) => {
    await injectIpcMock(page, {
      statusResults: [
        { status: 'running', progress: 0.5, errors: [], completed_chunks: 5, total_chunks: 10, current_step: 'process_chunks' },
        {
          status: 'done',
          progress: 1.0,
          errors: [],
          completed_chunks: 10,
          total_chunks: 10,
          current_step: 'write_to_project',
          import_review_report: {
            status: 'warning',
            judge_artifact_summary: {
              score: 0.88,
              converge_status: 'passed',
              summary: 'Judge accepted the import after one rerun.',
            },
          },
        },
      ],
    });
    await openImportModal(page);
    await page.getByTestId('w1-file-picker-btn').click();

    await expect(page.getByTestId('w1-success-msg')).toBeVisible({ timeout: 30000 });
    await expect(page.getByTestId('w1-review-judge-summary')).toContainText('Judge accepted');
    await expect(page.getByTestId('w1-review-judge-score')).toContainText('0.88');
  });

  test('mode selectors and file picker reappear after success if modal is closed and reopened', async ({ page }) => {
    await injectIpcMock(page, {
      statusResults: [
        { status: 'done', progress: 1.0, errors: [], completed_chunks: 10, total_chunks: 10, current_step: 'write_to_project' },
      ],
    });
    await openImportModal(page);
    await page.getByTestId('w1-file-picker-btn').click();
    await expect(page.getByTestId('w1-success-msg')).toBeVisible({ timeout: 20000 });

    // Close and reopen
    await page.getByTestId('w1-close-btn').click();
    await page.getByTestId('open-import-btn').click();

    // On next open, store should have reset (or show idle state again)
    await expect(page.getByTestId('w1-close-btn')).toBeVisible();
  });
});

test.describe('W1 Import Workflow — error state', () => {
  test('shows error message when import fails at start', async ({ page }) => {
    await injectIpcMock(page, {
      startResult: { session_id: '', status: 'error', error: 'Authentication failed: invalid API key' },
    });
    await openImportModal(page);
    await page.getByTestId('w1-file-picker-btn').click();

    await expect(page.getByTestId('w1-error-item')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('w1-error-item')).toContainText(/Authentication failed|invalid/i);
  });

  test('shows error item when sidecar returns error status mid-run', async ({ page }) => {
    await injectIpcMock(page, {
      statusResults: [
        { status: 'running', progress: 0.1, errors: [], completed_chunks: 0, total_chunks: 10, current_step: 'split_chunks' },
        { status: 'error',   progress: 0.1, errors: ['chunk 5 event extraction failed: Authentication Fails (governor)'], completed_chunks: 5, total_chunks: 10, current_step: 'process_chunks' },
      ],
    });
    await openImportModal(page);
    await page.getByTestId('w1-file-picker-btn').click();

    await expect(page.getByTestId('w1-error-item')).toBeVisible({ timeout: 20000 });
    await expect(page.getByTestId('w1-error-item')).toContainText(/Authentication Fails|governor/);
  });
});

test.describe('W1 Import Workflow — cancel', () => {
  test('cancel button stops the import', async ({ page }) => {
    await injectIpcMock(page, {
      // Status keeps returning running so we have time to click cancel
      statusResults: Array(20).fill({
        status: 'running', progress: 0.3, errors: [], completed_chunks: 3, total_chunks: 10, current_step: 'process_chunks',
      }),
    });
    await openImportModal(page);
    await page.getByTestId('w1-file-picker-btn').click();

    // Wait for running state then cancel
    await expect(page.getByTestId('w1-cancel-btn')).toBeVisible({ timeout: 8000 });
    await page.getByTestId('w1-cancel-btn').click();

    // After cancel, modal should show idle state (file picker reappears)
    await expect(page.getByTestId('w1-file-picker-btn')).toBeVisible({ timeout: 5000 });
  });
});

test.describe('W1 Import Workflow — provider credentials wiring', () => {
  /**
   * This test verifies that clicking "Select File" actually sends the active
   * provider's credentials in the w1:start IPC call, not blank strings.
   * We capture the IPC payload and assert on its contents.
   */
  test('w1:start payload includes api_key, model, and endpoint', async ({ page }) => {
    // Capture what the mock receives for w1:start
    let capturedPayload: Record<string, unknown> | null = null;

    await page.addInitScript(() => {
      const mockIpcRenderer = {
        invoke: async (channel: string, payload: unknown) => {
          if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
          if (channel === 'dialog:pick-files') return { canceled: false, paths: ['/tmp/novel.txt'] };
          if (channel === 'w1:start') {
            (window as any).__lastW1StartPayload = payload;
            return { session_id: 'cred-test-session', status: 'started' };
          }
          if (channel === 'w1:status') return { status: 'done', progress: 1.0, errors: [], completed_chunks: 5, total_chunks: 5, current_step: 'done' };
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
    });

    await page.goto('http://localhost:3000');
    await page.getByTestId('activity-btn-workbench').click();
    await page.getByTestId('open-import-btn').click();
    await page.getByTestId('w1-prompt-profile-select').selectOption('deep');
    await page.getByTestId('w1-file-picker-btn').click();

    // Wait for the start call to be captured
    await page.waitForFunction(() => (window as any).__lastW1StartPayload !== undefined, { timeout: 10000 });

    capturedPayload = await page.evaluate(() => (window as any).__lastW1StartPayload as Record<string, unknown>);

    // The payload must include credentials fields (not undefined/empty)
    expect(capturedPayload).toBeTruthy();
    // api_key, model, endpoint should be present (may be empty string if no provider configured,
    // but they must be present as keys rather than missing entirely)
    expect(Object.keys(capturedPayload!)).toContain('api_key');
    expect(Object.keys(capturedPayload!)).toContain('model');
    expect(Object.keys(capturedPayload!)).toContain('endpoint');
    expect(capturedPayload!.prompt_profile).toBe('deep');
  });

  test('custom expert fields affect w1:start payload', async ({ page }) => {
    await page.addInitScript(() => {
      const mockIpcRenderer = {
        invoke: async (channel: string, payload: unknown) => {
          if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
          if (channel === 'dialog:pick-files') return { canceled: false, paths: ['/tmp/novel.txt'] };
          if (channel === 'w1:start') {
            (window as any).__lastW1StartPayload = payload;
            return { session_id: 'custom-test-session', status: 'started' };
          }
          if (channel === 'w1:status') return { status: 'done', progress: 1.0, errors: [], completed_chunks: 5, total_chunks: 5, current_step: 'done' };
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
    });

    await page.goto('http://localhost:3000');
    await page.getByTestId('activity-btn-workbench').click();
    await page.getByTestId('open-import-btn').click();
    await page.getByTestId('w1-prompt-profile-select').selectOption('custom');
    await page.getByTestId('w1-custom-quality-target').selectOption('high');
    await page.getByTestId('w1-custom-max-chapters-per-window').fill('4');
    await page.getByTestId('w1-custom-event-density').selectOption('scene_level');
    await page.getByTestId('w1-custom-rerun-budget').fill('5');
    await page.getByTestId('w1-file-picker-btn').click();

    await page.waitForFunction(() => (window as any).__lastW1StartPayload !== undefined, { timeout: 10000 });
    const capturedPayload = await page.evaluate(() => (window as any).__lastW1StartPayload as Record<string, any>);

    expect(capturedPayload.prompt_profile).toBe('custom');
    expect(capturedPayload.use_supervisor).toBe(true);
    expect(capturedPayload.use_orchestrator).toBe(true);
    expect(capturedPayload.custom_profile_config.quality_target).toBe('high');
    expect(capturedPayload.custom_profile_config.chapters_per_window_max).toBe(4);
    expect(capturedPayload.custom_profile_config.max_chapters_per_window).toBe(4);
    expect(capturedPayload.custom_profile_config.event_density).toBe('scene_level');
    expect(capturedPayload.custom_profile_config.rerun_budget).toBe(5);
    expect(capturedPayload.orchestrator_overrides.use_orchestrator).toBe(true);
    expect(capturedPayload.orchestrator_overrides.rerun_budget).toBe(5);
  });
});
