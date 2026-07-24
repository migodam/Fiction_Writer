/**
 * Import workflow preset picker + extraction toggles — Playwright E2E tests.
 * Verifies the new IMPORT_PRESETS UI: all preset buttons render, selection
 * highlights the active preset, extraction toggles appear/disappear correctly,
 * and the IPC w1:start payload encodes the expected profile for each preset.
 *
 * All IPC is mocked; no sidecar or live API needed.
 */
import { test, expect, Page } from '@playwright/test';
import { TEST_NARRATIVE_IDE_INVOKE_METHODS } from '../helpers/narrativeIdeBridge';

async function injectIpcMockWithPayloadCapture(page: Page) {
  await page.addInitScript(({ bridgeMethods }) => {
    (window as any).__lastStartPayload = null;
    const mockIpcRenderer = {
      invoke: async (channel: string, payload: unknown) => {
        if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
        if (channel === 'dialog:pick-files') return { canceled: false, paths: ['/tmp/test-novel.txt'] };
        if (channel === 'w1:start') {
          (window as any).__lastStartPayload = payload;
          return { session_id: 'mock-preset-001', status: 'started' };
        }
        if (channel === 'w1:status') return { status: 'running', progress: 0.1, errors: [], completed_chunks: 0, total_chunks: 10, current_step: 'split_chunks' };
        if (channel === 'w1:console') return { entries: [], activity_entries: [], paused: false, breakpoint_chunk: null };
        if (channel === 'w1:cancel') return { status: 'cancelled' };
        return {};
      },
      on: () => {},
      removeAllListeners: () => {},
      send: () => {},
    };
    (window as any).narrativeIDE = Object.fromEntries(
      Object.entries(bridgeMethods).map(([method, channel]) => [
        method,
        (payload: unknown) => mockIpcRenderer.invoke(channel, payload),
      ]),
    );
  }, { bridgeMethods: TEST_NARRATIVE_IDE_INVOKE_METHODS });
}

async function openImportModal(page: Page) {
  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();
  await expect(page.getByTestId('w1-file-picker-btn')).toBeVisible();
}

test.describe('Import workflow — preset picker', () => {
  test('shows all 8 named preset options', async ({ page }) => {
    await injectIpcMockWithPayloadCapture(page);
    await openImportModal(page);

    const presetList = page.getByTestId('import-preset-list');
    await expect(presetList).toBeVisible();

    const expectedLabels = [
      'Auto (Orchestrator decides)',
      'Sparse turning points',
      'Chapter-level',
      'Scene-level',
      'Character-rich',
      'Relationship-light',
      'Manuscript-focused',
      'Advanced (custom)',
    ];
    for (const label of expectedLabels) {
      await expect(presetList).toContainText(label);
    }
  });

  test('auto preset is active by default', async ({ page }) => {
    await injectIpcMockWithPayloadCapture(page);
    await openImportModal(page);

    const autoBtn = page.getByTestId('preset-auto');
    await expect(autoBtn).toBeVisible();
    // Auto button has brand border when active
    await expect(autoBtn).toHaveClass(/border-brand/);
  });

  test('selecting sparse_turning_points highlights it and deselects auto', async ({ page }) => {
    await injectIpcMockWithPayloadCapture(page);
    await openImportModal(page);

    await page.getByTestId('preset-sparse_turning_points').click();

    await expect(page.getByTestId('preset-sparse_turning_points')).toHaveClass(/border-brand/);
    await expect(page.getByTestId('preset-auto')).not.toHaveClass(/border-brand/);
  });

  test('selecting sparse_turning_points sends custom profile to w1:start', async ({ page }) => {
    await injectIpcMockWithPayloadCapture(page);
    await openImportModal(page);

    await page.getByTestId('preset-sparse_turning_points').click();
    await page.getByTestId('w1-file-picker-btn').click();

    await page.waitForFunction(() => (window as any).__lastStartPayload !== null, { timeout: 5000 });
    const payload = await page.evaluate(() => (window as any).__lastStartPayload);
    expect(payload.prompt_profile).toBe('custom');
    expect(payload.use_supervisor).toBe(true);
    expect(payload.use_orchestrator).toBe(true);
    expect(payload.custom_profile_config?.event_density).toBe('arc_level');
    expect(payload.custom_profile_config?.character_granularity).toBe('major_only');
  });

  test('balanced auto import never sends supervisor false', async ({ page }) => {
    await injectIpcMockWithPayloadCapture(page);
    await openImportModal(page);

    await page.getByTestId('w1-file-picker-btn').click();
    await page.waitForFunction(() => (window as any).__lastStartPayload !== null, { timeout: 5000 });
    const payload = await page.evaluate(() => (window as any).__lastStartPayload);
    expect(payload.import_mode).toBe('import_all');
    expect(payload.use_supervisor).toBe(true);
    expect(payload.use_orchestrator).toBe(true);
  });

  test('selecting manuscript_focused sends import_content_only mode', async ({ page }) => {
    await injectIpcMockWithPayloadCapture(page);
    await openImportModal(page);

    await page.getByTestId('preset-manuscript_focused').click();
    await page.getByTestId('w1-file-picker-btn').click();

    await page.waitForFunction(() => (window as any).__lastStartPayload !== null, { timeout: 5000 });
    const payload = await page.evaluate(() => (window as any).__lastStartPayload);
    expect(payload.import_mode).toBe('import_content_only');
  });

  test('extraction toggles hidden for manuscript_focused preset', async ({ page }) => {
    await injectIpcMockWithPayloadCapture(page);
    await openImportModal(page);

    await page.getByTestId('preset-manuscript_focused').click();
    await expect(page.getByTestId('toggle-extract-relationships')).not.toBeVisible();
    await expect(page.getByTestId('toggle-extract-world')).not.toBeVisible();
    await expect(page.getByTestId('toggle-extract-timeline')).not.toBeVisible();
  });

  test('extraction toggles visible for non-manuscript presets', async ({ page }) => {
    await injectIpcMockWithPayloadCapture(page);
    await openImportModal(page);

    // auto preset is default — toggles should be visible
    await expect(page.getByTestId('toggle-extract-relationships')).toBeVisible();
    await expect(page.getByTestId('toggle-extract-world')).toBeVisible();
    await expect(page.getByTestId('toggle-extract-timeline')).toBeVisible();
    // All checked by default
    await expect(page.getByTestId('toggle-extract-relationships')).toBeChecked();
  });

  test('unchecking extract_relationships sends false in payload', async ({ page }) => {
    await injectIpcMockWithPayloadCapture(page);
    await openImportModal(page);

    await page.getByTestId('toggle-extract-relationships').uncheck();
    await expect(page.getByTestId('toggle-extract-relationships')).not.toBeChecked();

    await page.getByTestId('w1-file-picker-btn').click();
    await page.waitForFunction(() => (window as any).__lastStartPayload !== null, { timeout: 5000 });
    const payload = await page.evaluate(() => (window as any).__lastStartPayload);
    expect(payload.custom_profile_config?.extract_relationships).toBe(false);
  });

  test('advanced preset shows expert panel knobs', async ({ page }) => {
    await injectIpcMockWithPayloadCapture(page);
    await openImportModal(page);

    // Expert panel hidden by default
    await expect(page.getByTestId('w1-custom-expert-panel')).not.toBeVisible();

    await page.getByTestId('preset-advanced').click();
    await expect(page.getByTestId('w1-custom-expert-panel')).toBeVisible();
    await expect(page.getByTestId('w1-custom-quality-target')).toBeVisible();
    await expect(page.getByTestId('w1-custom-event-density')).toBeVisible();
  });
});
