/**
 * Worker F — Token / Cost card E2E tests.
 * All IPC is mocked; no sidecar or live API needed.
 */
import { test, expect, Page } from '@playwright/test';

// ── IPC mock helper (same pattern as import_workflow.spec.ts) ────────────────

type StatusResult = {
  status: string;
  progress: number;
  errors: string[];
  completed_chunks: number;
  total_chunks: number;
  current_step: string;
  extraction_counts?: { characters: number; events: number; world_items: number; relationships: number };
  token_ledger?: {
    actual_input_tokens: number;
    actual_output_tokens: number;
    actual_total_tokens: number;
    api_call_count: number;
    estimated_input_tokens: number;
    cost_usd?: number;
    cost_unavailable_reason?: string;
  };
};

async function injectIpcMock(page: Page, statusResults: StatusResult[]) {
  await page.addInitScript(
    ({ statusResults }) => {
      let statusCallCount = 0;
      const mockIpcRenderer = {
        invoke: async (channel: string, _payload: unknown) => {
          if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
          if (channel === 'dialog:pick-files') return { canceled: false, paths: ['/tmp/test-novel.txt'] };
          if (channel === 'w1:start') return { session_id: 'mock-f-001', status: 'started' };
          if (channel === 'w1:status') {
            const idx = Math.min(statusCallCount, statusResults.length - 1);
            statusCallCount++;
            return statusResults[idx];
          }
          if (channel === 'w1:console') return { entries: [], activity_entries: [], paused: false, breakpoint_chunk: null };
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
    { statusResults }
  );
}

async function openImportModal(page: Page) {
  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();
  await expect(page.getByTestId('w1-file-picker-btn')).toBeVisible();
}

// ── Test fixtures ─────────────────────────────────────────────────────────────

// formatTokens: n >= 1000 → `${(n/1000).toFixed(1)}k`
// 45000 → "45.0k", 90000 → "90.0k", 12000 → "12.0k"

const withActualUsage: StatusResult[] = [
  {
    status: 'running',
    progress: 0.5,
    errors: [],
    completed_chunks: 5,
    total_chunks: 10,
    current_step: 'process_chunks',
    extraction_counts: { characters: 3, events: 5, world_items: 2, relationships: 1 },
    token_ledger: {
      actual_input_tokens: 45000,
      actual_output_tokens: 12000,
      actual_total_tokens: 57000,
      api_call_count: 9,
      estimated_input_tokens: 48000,
      cost_usd: 0.0254,
    },
  },
  {
    status: 'done',
    progress: 1.0,
    errors: [],
    completed_chunks: 10,
    total_chunks: 10,
    current_step: 'write_to_project',
    token_ledger: {
      actual_input_tokens: 90000,
      actual_output_tokens: 24000,
      actual_total_tokens: 114000,
      api_call_count: 20,
      estimated_input_tokens: 96000,
      cost_usd: 0.0507,
    },
  },
];

const estimateOnly: StatusResult[] = [
  {
    status: 'running',
    progress: 0.1,
    errors: [],
    completed_chunks: 1,
    total_chunks: 10,
    current_step: 'process_chunks',
    token_ledger: {
      actual_input_tokens: 0,
      actual_output_tokens: 0,
      actual_total_tokens: 0,
      api_call_count: 0,
      estimated_input_tokens: 32000,
      cost_unavailable_reason: 'No price configured for model: unknown-model',
    },
  },
  { status: 'done', progress: 1.0, errors: [], completed_chunks: 10, total_chunks: 10, current_step: 'done' },
];

const budgetExhausted: StatusResult[] = [
  {
    status: 'running',
    progress: 0.3,
    errors: ['402: Insufficient balance (budget_exhausted)'],
    completed_chunks: 3,
    total_chunks: 10,
    current_step: 'process_chunks',
    token_ledger: {
      actual_input_tokens: 12000,
      actual_output_tokens: 4000,
      actual_total_tokens: 16000,
      api_call_count: 3,
      estimated_input_tokens: 48000,
      cost_usd: 0.0075,
    },
  },
];

const noLedger: StatusResult[] = [
  { status: 'running', progress: 0.2, errors: [], completed_chunks: 2, total_chunks: 10, current_step: 'split_chunks' },
  { status: 'done', progress: 1.0, errors: [], completed_chunks: 10, total_chunks: 10, current_step: 'done' },
];

// ── Tests ─────────────────────────────────────────────────────────────────────

test.describe('W1 Import — Token / Cost card', () => {
  test('renders token/cost card with actual usage during running', async ({ page }) => {
    await injectIpcMock(page, withActualUsage);
    await openImportModal(page);
    await page.getByTestId('w1-file-picker-btn').click();

    await expect(page.getByTestId('w1-token-cost-card')).toBeVisible({ timeout: 8000 });
    // 45000 tokens → "45.0k"
    await expect(page.getByTestId('w1-token-cost-input')).toContainText('45');
    await expect(page.getByTestId('w1-token-cost-calls')).toContainText('9');
    // cost_usd 0.0254 → "$0.0254"
    await expect(page.getByTestId('w1-token-cost-estimated-cost')).toContainText('$0.0254');
  });

  test('token/cost card persists on done status with final totals', async ({ page }) => {
    await injectIpcMock(page, withActualUsage);
    await openImportModal(page);
    await page.getByTestId('w1-file-picker-btn').click();

    // Wait for the card to appear (may show running state first)
    await expect(page.getByTestId('w1-token-cost-card')).toBeVisible({ timeout: 10000 });

    // Wait for done status (success message appears)
    await expect(page.getByTestId('w1-success-msg')).toBeVisible({ timeout: 15000 });

    // Card must still be present after done — it renders outside running/paused guard
    await expect(page.getByTestId('w1-token-cost-card')).toBeVisible();
    // Final totals: 90000 → "90.0k", api_call_count 20, cost_usd 0.0507
    await expect(page.getByTestId('w1-token-cost-input')).toContainText('90');
    await expect(page.getByTestId('w1-token-cost-calls')).toContainText('20');
    await expect(page.getByTestId('w1-token-cost-estimated-cost')).toContainText('$0.0507');
  });

  test('shows estimated tokens when actual usage is zero', async ({ page }) => {
    await injectIpcMock(page, estimateOnly);
    await openImportModal(page);
    await page.getByTestId('w1-file-picker-btn').click();

    await expect(page.getByTestId('w1-token-cost-card')).toBeVisible({ timeout: 8000 });
    // actual_input_tokens is 0, so formatted as estimated: "32.0k (est.)"
    await expect(page.getByTestId('w1-token-cost-input')).toContainText('est.');
    // cost_unavailable_reason shown in place of cost_usd
    await expect(page.getByTestId('w1-token-cost-estimated-cost')).toContainText('No price configured');
  });

  test('402 budget-exhausted banner appears during running with budget error', async ({ page }) => {
    await injectIpcMock(page, budgetExhausted);
    await openImportModal(page);
    await page.getByTestId('w1-file-picker-btn').click();

    await expect(page.getByTestId('w1-budget-exhausted-banner')).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId('w1-budget-exhausted-banner')).toContainText('402');
    await expect(page.getByTestId('w1-token-cost-card')).toBeVisible();
  });

  test('token/cost card absent when status has no token_ledger', async ({ page }) => {
    await injectIpcMock(page, noLedger);
    await openImportModal(page);
    await page.getByTestId('w1-file-picker-btn').click();

    // Allow time for polling — card must not appear
    await page.waitForTimeout(3000);
    await expect(page.getByTestId('w1-token-cost-card')).not.toBeVisible();
  });
});
