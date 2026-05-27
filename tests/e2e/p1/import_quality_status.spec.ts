/**
 * Import quality status tests — verifies acceptable_with_warnings color,
 * warnings expand toggle, and judge summary rendering.
 *
 * Mirrors the window.require override + MockState pattern from
 * import_workflow.spec.ts. Helpers are local to keep the file self-contained.
 */
import { expect, test, type Page } from '@playwright/test';

// ── IPC mock helpers (same pattern as import_workflow.spec.ts) ────────────────

interface StatusResult {
  status: string;
  progress: number;
  errors: string[];
  completed_chunks: number;
  total_chunks: number;
  current_step: string;
  import_review_report?: Record<string, unknown>;
  judge_artifact_summary?: Record<string, unknown>;
}

interface MockState {
  startResult: { session_id: string; status: string };
  statusResults: StatusResult[];
  statusCallCount: number;
}

async function injectIpcMock(page: Page, statusResults: StatusResult[]) {
  await page.addInitScript(
    ({ startResult, statusResults }) => {
      const state: MockState = { startResult, statusResults, statusCallCount: 0 };
      (window as any).__mockIpcState = state;

      const mockIpcRenderer = {
        invoke: async (channel: string) => {
          const s = (window as any).__mockIpcState as MockState;
          if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
          if (channel === 'dialog:pick-files') return { canceled: false, paths: ['/tmp/test.txt'] };
          if (channel === 'w1:start') return s.startResult;
          if (channel === 'w1:status') {
            const idx = Math.min(s.statusCallCount, s.statusResults.length - 1);
            const result = s.statusResults[idx];
            s.statusCallCount += 1;
            return result;
          }
          if (channel === 'w1:cancel') return { status: 'cancelled' };
          if (channel === 'w1:console') return { entries: [] };
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
    {
      startResult: { session_id: 'mock-quality-001', status: 'started' },
      statusResults,
    },
  );
}

async function openImportModal(page: Page) {
  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();
  await expect(page.getByTestId('w1-file-picker-btn')).toBeVisible();
}

async function triggerAndWaitForDone(page: Page) {
  await page.getByTestId('w1-file-picker-btn').click();
  await expect(page.getByTestId('w1-review-step')).toBeVisible({ timeout: 12_000 });
}

// ── Fixture status results ────────────────────────────────────────────────────

const ACCEPTABLE_WITH_WARNINGS_RESULTS: StatusResult[] = [
  {
    status: 'running',
    progress: 0.5,
    errors: [],
    completed_chunks: 3,
    total_chunks: 5,
    current_step: 'process_chunks',
  },
  {
    status: 'done',
    progress: 1.0,
    errors: [],
    completed_chunks: 5,
    total_chunks: 5,
    current_step: 'write_to_project',
    judge_artifact_summary: {
      score: 0.72,
      converge_status: 'converged',
      summary: 'Import meets minimum thresholds with narrative gaps noted.',
      required_reruns: [],
    },
    import_review_report: {
      status: 'acceptable_with_warnings',
      warnings: [
        'Event coverage below threshold: 8 of 12 chapters have events',
        'Branch topology flat: no fork/merge arcs detected',
        'Character count below target: 4 of 6 major characters extracted',
        'World items sparse: fewer than 3 locations per act',
        'Faction arcs absent: no parallel political timeline branches',
        'Rerun budget exhausted without full convergence',
      ],
      failed_chunks: [],
      safe_accept_ids: [],
      judge_artifact_summary: {
        score: 0.72,
        converge_status: 'converged',
        summary: 'Import meets minimum thresholds with narrative gaps noted.',
        required_reruns: [],
      },
    },
  },
];

const PASS_RESULTS: StatusResult[] = [
  {
    status: 'running',
    progress: 0.5,
    errors: [],
    completed_chunks: 3,
    total_chunks: 5,
    current_step: 'process_chunks',
  },
  {
    status: 'done',
    progress: 1.0,
    errors: [],
    completed_chunks: 5,
    total_chunks: 5,
    current_step: 'write_to_project',
    import_review_report: {
      status: 'pass',
      warnings: [],
      failed_chunks: [],
      safe_accept_ids: [],
      judge_artifact_summary: {
        score: 0.92,
        converge_status: 'converged',
        summary: 'Full import quality achieved.',
        required_reruns: [],
      },
    },
  },
];

// ── Suite: acceptable_with_warnings ──────────────────────────────────────────

test.describe('Import review status: acceptable_with_warnings', () => {
  test.beforeEach(async ({ page }) => {
    await injectIpcMock(page, ACCEPTABLE_WITH_WARNINGS_RESULTS);
    await openImportModal(page);
  });

  test('review status text is acceptable_with_warnings', async ({ page }) => {
    await triggerAndWaitForDone(page);
    await expect(page.getByTestId('w1-review-status')).toHaveText('acceptable_with_warnings');
  });

  test('review status element has amber color class', async ({ page }) => {
    await triggerAndWaitForDone(page);
    await expect(page.getByTestId('w1-review-status')).toHaveClass(/text-amber/);
  });

  test('only 4 warnings shown initially', async ({ page }) => {
    await triggerAndWaitForDone(page);
    const warningsContainer = page.getByTestId('w1-review-warnings');
    await expect(warningsContainer).toBeVisible();
    const items = await warningsContainer.locator('li').all();
    expect(items.length).toBe(4);
  });

  test('show-more toggle is visible when warnings > 4', async ({ page }) => {
    await triggerAndWaitForDone(page);
    await expect(page.getByTestId('w1-review-warnings-toggle')).toBeVisible();
    const toggleText = await page.getByTestId('w1-review-warnings-toggle').textContent();
    expect(toggleText).toMatch(/Show 2 more/);
  });

  test('clicking show-more reveals all 6 warnings and shows "Show less"', async ({ page }) => {
    await triggerAndWaitForDone(page);
    await page.getByTestId('w1-review-warnings-toggle').click();
    const items = await page.getByTestId('w1-review-warnings').locator('li').all();
    expect(items.length).toBe(6);
    await expect(page.getByTestId('w1-review-warnings-toggle')).toHaveText('Show less');
  });

  test('judge summary card shows score and converge status', async ({ page }) => {
    await triggerAndWaitForDone(page);
    await expect(page.getByTestId('w1-review-judge-summary')).toBeVisible();
    await expect(page.getByTestId('w1-review-judge-score')).toContainText('0.72');
    await expect(page.getByTestId('w1-review-converge-status')).toContainText('converged');
  });
});

// ── Suite: pass status ────────────────────────────────────────────────────────

test.describe('Import review status: pass', () => {
  test.beforeEach(async ({ page }) => {
    await injectIpcMock(page, PASS_RESULTS);
    await openImportModal(page);
  });

  test('pass status renders with green color class', async ({ page }) => {
    await triggerAndWaitForDone(page);
    await expect(page.getByTestId('w1-review-status')).toHaveText('pass');
    await expect(page.getByTestId('w1-review-status')).toHaveClass(/text-green/);
  });

  test('no warnings toggle shown when warnings list is empty', async ({ page }) => {
    await triggerAndWaitForDone(page);
    await expect(page.getByTestId('w1-review-warnings-toggle')).not.toBeVisible();
  });
});

// ── Suite: responsive viewports ──────────────────────────────────────────────

test.describe('Import review UI: responsive viewports', () => {
  const VIEWPORTS = [
    { label: '1280x800', width: 1280, height: 800 },
    { label: '1024x768', width: 1024, height: 768 },
  ];

  for (const vp of VIEWPORTS) {
    test(`import modal review step accessible at ${vp.label}`, async ({ page }) => {
      await injectIpcMock(page, ACCEPTABLE_WITH_WARNINGS_RESULTS);
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await openImportModal(page);
      await triggerAndWaitForDone(page);
      await expect(page.getByTestId('w1-review-step')).toBeVisible();
      await expect(page.getByTestId('w1-review-status')).toBeVisible();
    });
  }
});
