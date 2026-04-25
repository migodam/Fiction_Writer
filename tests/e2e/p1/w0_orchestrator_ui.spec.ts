import { test, expect, Page } from '@playwright/test';

type W0StatusResult = {
  status: string;
  current_step: number;
  total_steps: number;
  progress: number;
  pending_permission: null | {
    step_id: string;
    description: string;
    risk_level: string;
    affected_entities: string[];
  };
  plan: Array<{
    step_id: string;
    workflow: string;
    rationale: string;
    status: string;
    requires_permission?: boolean;
  }>;
  errors: string[];
};

async function injectOrchestratorMock(page: Page, statusResults: W0StatusResult[]) {
  await page.addInitScript(({ statusResults }) => {
    const state = {
      statusResults,
      statusCallCount: 0,
      granted: false,
      denied: false,
    };
    (window as any).__w0MockState = state;

    const mockIpcRenderer = {
      invoke: async (channel: string, payload: unknown) => {
        const s = (window as any).__w0MockState;
        if (channel === 'settings:load-app') return null;
        if (channel === 'settings:save-app') return payload;
        if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
        if (channel === 'orchestrator:start') {
          (window as any).__lastW0StartPayload = payload;
          return { session_id: 'w0-session-001', status: 'started', plan: [] };
        }
        if (channel === 'orchestrator:status') {
          const idx = Math.min(s.statusCallCount, s.statusResults.length - 1);
          const result = s.statusResults[idx];
          s.statusCallCount += 1;
          return result;
        }
        if (channel === 'orchestrator:grant') {
          s.granted = true;
          return { status: 'granted', step_id: 'step_import' };
        }
        if (channel === 'orchestrator:deny') {
          s.denied = true;
          return { status: 'denied', step_id: 'step_import' };
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
  }, { statusResults });
}

const runningStatus: W0StatusResult = {
  status: 'executing',
  current_step: 0,
  total_steps: 2,
  progress: 0.35,
  pending_permission: null,
  plan: [
    { step_id: 'step_import', workflow: 'W1', rationale: 'Import source manuscript.', status: 'running', requires_permission: true },
    { step_id: 'step_audit', workflow: 'W4', rationale: 'Check continuity after import.', status: 'pending' },
  ],
  errors: [],
};

test.describe('W0 Orchestrator UI', () => {
  test('starts W0 and renders plan/progress/result state', async ({ page }) => {
    await injectOrchestratorMock(page, [
      runningStatus,
      {
        ...runningStatus,
        status: 'done',
        current_step: 2,
        progress: 1,
        plan: runningStatus.plan.map((step) => ({ ...step, status: 'completed' })),
      },
    ]);

    await page.goto('http://localhost:3000/agents/console');
    await expect(page.getByTestId('w0-orchestrator-panel')).toBeVisible();

    await page.getByTestId('w0-goal-input').fill('Import the manuscript and run consistency checks.');
    await page.getByTestId('w0-start-btn').click();

    await expect(page.getByTestId('w0-plan-step-0')).toContainText('W1', { timeout: 8000 });
    await expect(page.getByTestId('w0-progress-label')).toContainText('35');
    await expect(page.getByTestId('w0-result-card')).toBeVisible({ timeout: 12000 });

    const payload = await page.evaluate(() => (window as any).__lastW0StartPayload as Record<string, unknown>);
    expect(payload.goal).toBe('Import the manuscript and run consistency checks.');
    expect(Object.keys(payload)).toContain('api_key');
    expect(Object.keys(payload)).toContain('model');
    expect(Object.keys(payload)).toContain('endpoint');
  });

  test('shows permission request and grants it', async ({ page }) => {
    await injectOrchestratorMock(page, [
      {
        ...runningStatus,
        status: 'waiting_permission',
        progress: 0.2,
        pending_permission: {
          step_id: 'step_import',
          description: 'Run W1: Import source manuscript.',
          risk_level: 'high',
          affected_entities: ['source_file_path'],
        },
      },
      {
        ...runningStatus,
        status: 'done',
        current_step: 2,
        progress: 1,
        plan: runningStatus.plan.map((step) => ({ ...step, status: 'completed' })),
      },
    ]);

    await page.goto('http://localhost:3000/agents/console');
    await page.getByTestId('w0-goal-input').fill('Import a new source file.');
    await page.getByTestId('w0-start-btn').click();

    await expect(page.getByTestId('w0-permission-card')).toBeVisible({ timeout: 8000 });
    await expect(page.getByTestId('w0-permission-card')).toContainText('Run W1');
    await page.getByTestId('w0-grant-btn').click();

    await expect(page.getByTestId('w0-result-card')).toBeVisible({ timeout: 12000 });
    const granted = await page.evaluate(() => (window as any).__w0MockState.granted as boolean);
    expect(granted).toBe(true);
  });
});
