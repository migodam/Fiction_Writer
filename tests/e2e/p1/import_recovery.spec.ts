import { expect, test } from '@playwright/test';
import { TEST_NARRATIVE_IDE_INVOKE_METHODS } from '../helpers/narrativeIdeBridge';

test('recovery discovery is attempt-scoped, dedupes reconnect events, and forks checkpoints', async ({ page }) => {
  await page.addInitScript((bridgeMethods) => {
    const snapshotRef = (checkpointId: string) => ({ contract_version: 'W1SupervisorSnapshot/v1', relative_path: `system/imports/lineage-parent/attempts/attempt-parent/snapshots/${checkpointId}`, manifest_sha256: 'a'.repeat(64), snapshot_sha256: 'b'.repeat(64), source_identity_sha256: 'c'.repeat(64), config_identity_sha256: 'd'.repeat(64), lineage_id: 'lineage-parent', attempt_id: 'attempt-parent', checkpoint_id: checkpointId });
    const state = { resumeCalls: 0, forkCalls: 0, pauseCalls: 0, cancelCalls: 0, eventCalls: 0, actionPayloads: [] as Array<{ channel: string; payload: Record<string, unknown> }> };
    (window as any).__recoveryState = state;
    const invoke = async (channel: string, payload: Record<string, unknown> = {}) => {
      if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
      if (channel === 'runtime:recoverable') return {
        runs: [{ lineage_id: 'lineage-1', attempt_id: 'attempt-1', status: 'recoverable', completed: 2, remaining: 3, source_compatible: true, api_cost_usd: 0.42 }],
      };
      if (channel === 'runtime:run') return { lineage_id: 'lineage-1', attempt_id: 'attempt-1', status: 'recoverable' };
      if (channel === 'runtime:events') {
        state.eventCalls += 1;
        return { events: state.eventCalls === 1
          ? [{ event_id: 'event-1', sequence: 1, event_type: 'agent.started', payload: { agent_id: 'scout', summary: 'Scout started' }}, { event_id: 'event-3', sequence: 3, event_type: 'agent.completed', payload: { agent_id: 'scout', summary: 'Scout completed' }}]
          : [{ event_id: 'event-3', sequence: 3, event_type: 'agent.completed', payload: { agent_id: 'scout', summary: 'Scout completed' }}] };
      }
      if (channel === 'runtime:checkpoints') return { checkpoints: [{ checkpoint_id: 'checkpoint-1', sequence: 1, label: 'After source scan', metadata: { resumable: true, snapshot_ref: snapshotRef('checkpoint-1') } }] };
      if (channel.startsWith('runtime:') && ['runtime:resume', 'runtime:fork', 'runtime:pause', 'runtime:cancel'].includes(channel)) state.actionPayloads.push({ channel, payload });
      if (channel === 'runtime:resume') { state.resumeCalls += 1; return { attempt_id: 'attempt-2', status: 'running' }; }
      if (channel === 'runtime:fork') {
        state.forkCalls += 1;
        return {
          attempt: { attempt_id: 'attempt-fork', status: 'paused' },
          parent_attempt_id: 'attempt-2',
          fork_snapshot: {
            resumable: true,
            state_reference: {
              kind: 'w1_supervisor_snapshot/v1',
              immutable: true,
              resumable: true,
              snapshot_ref: snapshotRef('checkpoint-1'),
            },
          },
        };
      }
      if (channel === 'runtime:pause') { state.pauseCalls += 1; return { attempt_id: 'attempt-1', status: 'paused' }; }
      if (channel === 'runtime:cancel') { state.cancelCalls += 1; return { attempt_id: 'attempt-1', status: 'cancelled' }; }
      return {};
    };
    (window as any).narrativeIDE = Object.fromEntries(Object.entries(bridgeMethods).map(([method, channel]) => [method, (payload: Record<string, unknown>) => invoke(channel, payload)]));
  }, TEST_NARRATIVE_IDE_INVOKE_METHODS);

  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();
  await expect(page.getByTestId('w1-recovery-center')).toBeVisible();
  await expect(page.getByTestId('w1-recovery-resume-lineage-1')).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as any).__recoveryState.resumeCalls)).toBe(0);
  await expect(page.getByTestId('w1-runtime-gap-warning')).toBeVisible();
  await expect(page.getByTestId('w1-runtime-agent-scout')).toBeVisible();
  await page.getByTestId('w1-runtime-pause').click();
  await page.getByTestId('w1-runtime-cancel').click();
  await expect.poll(() => page.evaluate(() => (window as any).__recoveryState.pauseCalls)).toBe(1);
  await expect.poll(() => page.evaluate(() => (window as any).__recoveryState.cancelCalls)).toBe(1);
  await expect.poll(() => page.evaluate(() => (window as any).__recoveryState.actionPayloads.map((entry: any) => ({ channel: entry.channel, attempt_id: entry.payload.attempt_id, decision_id: entry.payload.decision_id })))).toEqual([
    { channel: 'runtime:pause', attempt_id: 'attempt-1', decision_id: expect.any(String) },
    { channel: 'runtime:cancel', attempt_id: 'attempt-1', decision_id: expect.any(String) },
  ]);
  const controlIds = await page.evaluate(() => (window as any).__recoveryState.actionPayloads.map((entry: any) => entry.payload.decision_id));
  expect(new Set(controlIds).size).toBe(2);

  await page.getByTestId('w1-recovery-resume-lineage-1').click();
  await expect.poll(() => page.evaluate(() => (window as any).__recoveryState.resumeCalls)).toBe(1);
  await expect.poll(() => page.evaluate(() => (window as any).__recoveryState.actionPayloads.find((entry: any) => entry.channel === 'runtime:resume')?.payload.decision_id)).toEqual(expect.any(String));
  await page.getByTestId('w1-checkpoint-fork-checkpoint-1').click();
  await expect.poll(() => page.evaluate(() => (window as any).__recoveryState.forkCalls)).toBe(1);
  await expect.poll(() => page.evaluate(() => (window as any).__recoveryState.actionPayloads.find((entry: any) => entry.channel === 'runtime:fork'))).toMatchObject({
    channel: 'runtime:fork',
    payload: { attempt_id: 'attempt-2', checkpoint_id: 'checkpoint-1', decision_id: 'fork:attempt-2:checkpoint-1' },
  });
  await page.getByTestId('w1-runtime-pause').click();
  await expect.poll(() => page.evaluate(() => (window as any).__recoveryState.actionPayloads.filter((entry: any) => entry.channel === 'runtime:pause').at(-1))).toMatchObject({
    payload: { attempt_id: 'attempt-fork' },
  });
});

test('shows preview-only checkpoints with a real details panel and never forks them', async ({ page }) => {
  await page.addInitScript((bridgeMethods) => {
    const state = { forkCalls: 0 };
    (window as any).__previewOnlyState = state;
    const invoke = async (channel: string) => {
      if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
      if (channel === 'runtime:recoverable') return { runs: [{ lineage_id: 'lineage-preview', attempt_id: 'attempt-preview', status: 'recoverable', source_compatible: true }] };
      if (channel === 'runtime:events') return { events: [] };
      if (channel === 'runtime:checkpoints') return { checkpoints: [
        {
          checkpoint_id: 'checkpoint-preview', sequence: 3, label: 'Legacy checkpoint', summary: 'Source scan completed',
          metadata: { recovery_mode: 'preview_only', preview_reason: 'legacy_checkpoint_without_snapshot' },
        },
        {
          checkpoint_id: 'checkpoint-flag-only', sequence: 4, label: 'Missing snapshot reference',
          metadata: { resumable: true },
        },
      ] };
      if (channel === 'runtime:fork') { state.forkCalls += 1; return {}; }
      return {};
    };
    (window as any).narrativeIDE = Object.fromEntries(Object.entries(bridgeMethods).map(([method, channel]) => [method, () => invoke(channel)]));
  }, TEST_NARRATIVE_IDE_INVOKE_METHODS);

  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();

  await expect(page.getByTestId('w1-checkpoint-status-checkpoint-preview')).toContainText('Preview only');
  await expect(page.getByTestId('w1-checkpoint-reason-checkpoint-preview')).toContainText('legacy_checkpoint_without_snapshot');
  const fork = page.getByTestId('w1-checkpoint-fork-checkpoint-preview');
  await expect(fork).toBeDisabled();
  await expect(fork).toHaveAttribute('aria-label', /Preview only/);
  await expect(page.getByTestId('w1-checkpoint-status-checkpoint-flag-only')).toContainText('Preview only');
  await expect(page.getByTestId('w1-checkpoint-fork-checkpoint-flag-only')).toBeDisabled();
  await expect(page.getByTestId('w1-checkpoint-fork-checkpoint-flag-only')).toHaveAttribute('aria-label', /no verified resumable snapshot/);
  await page.getByTestId('w1-checkpoint-preview-checkpoint-preview').click();
  await expect(page.getByTestId('w1-checkpoint-details-checkpoint-preview')).toContainText('Source scan completed');
  await expect.poll(() => page.evaluate(() => (window as any).__previewOnlyState.forkCalls)).toBe(0);
});

test('does not switch the active attempt when a fork response contains an error payload', async ({ page }) => {
  await page.addInitScript((bridgeMethods) => {
    const snapshotRef = (checkpointId: string) => ({ contract_version: 'W1SupervisorSnapshot/v1', relative_path: `system/imports/lineage-parent/attempts/attempt-parent/snapshots/${checkpointId}`, manifest_sha256: 'a'.repeat(64), snapshot_sha256: 'b'.repeat(64), source_identity_sha256: 'c'.repeat(64), config_identity_sha256: 'd'.repeat(64), lineage_id: 'lineage-parent', attempt_id: 'attempt-parent', checkpoint_id: checkpointId });
    const state = { calls: [] as Array<{ channel: string; payload: Record<string, unknown> }> };
    (window as any).__forkFailureState = state;
    const invoke = async (channel: string, payload: Record<string, unknown> = {}) => {
      if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
      if (channel === 'runtime:recoverable') return { runs: [{ lineage_id: 'lineage-parent', attempt_id: 'attempt-parent', status: 'recoverable', source_compatible: true }] };
      if (channel === 'runtime:events') return { events: [] };
      if (channel === 'runtime:checkpoints') return { checkpoints: [{ checkpoint_id: 'checkpoint-resumable', sequence: 4, metadata: { resumable: true, snapshot_ref: snapshotRef('checkpoint-resumable') } }] };
      if (channel === 'runtime:fork') {
        state.calls.push({ channel, payload });
        return { error: 'snapshot_validation_failed', attempt: { attempt_id: 'attempt-child', status: 'paused' }, fork_snapshot: { resumable: false, non_resumable_reason: 'snapshot_validation_failed' } };
      }
      if (channel === 'runtime:pause') {
        state.calls.push({ channel, payload });
        return { attempt_id: payload.attempt_id, status: 'paused' };
      }
      return {};
    };
    (window as any).narrativeIDE = Object.fromEntries(Object.entries(bridgeMethods).map(([method, channel]) => [method, (payload: Record<string, unknown>) => invoke(channel, payload)]));
  }, TEST_NARRATIVE_IDE_INVOKE_METHODS);

  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();
  await expect(page.getByTestId('w1-checkpoint-fork-checkpoint-resumable')).toBeEnabled();
  await page.getByTestId('w1-checkpoint-fork-checkpoint-resumable').click();
  await expect(page.getByTestId('w1-checkpoint-fork-error')).toContainText('active attempt was not changed');
  await page.getByTestId('w1-runtime-pause').click();
  await expect.poll(() => page.evaluate(() => (window as any).__forkFailureState.calls)).toEqual(expect.arrayContaining([
    expect.objectContaining({ channel: 'runtime:fork', payload: expect.objectContaining({ attempt_id: 'attempt-parent' }) }),
    expect.objectContaining({ channel: 'runtime:pause', payload: expect.objectContaining({ attempt_id: 'attempt-parent' }) }),
  ]));
});

test('does not trust a child resumable flag without a fork snapshot', async ({ page }) => {
  await page.addInitScript((bridgeMethods) => {
    const snapshotRef = (checkpointId: string) => ({ contract_version: 'W1SupervisorSnapshot/v1', relative_path: `system/imports/lineage-parent/attempts/attempt-parent/snapshots/${checkpointId}`, manifest_sha256: 'a'.repeat(64), snapshot_sha256: 'b'.repeat(64), source_identity_sha256: 'c'.repeat(64), config_identity_sha256: 'd'.repeat(64), lineage_id: 'lineage-parent', attempt_id: 'attempt-parent', checkpoint_id: checkpointId });
    const state = { calls: [] as Array<{ channel: string; payload: Record<string, unknown> }> };
    (window as any).__missingForkSnapshotState = state;
    const invoke = async (channel: string, payload: Record<string, unknown> = {}) => {
      if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
      if (channel === 'runtime:recoverable') return { runs: [{ lineage_id: 'lineage-parent', attempt_id: 'attempt-parent', status: 'recoverable', source_compatible: true }] };
      if (channel === 'runtime:events') return { events: [] };
      if (channel === 'runtime:checkpoints') return { checkpoints: [{ checkpoint_id: 'checkpoint-resumable', sequence: 4, metadata: { resumable: true, snapshot_ref: snapshotRef('checkpoint-resumable') } }] };
      if (channel === 'runtime:fork') {
        state.calls.push({ channel, payload });
        return { attempt: { attempt_id: 'attempt-child', status: 'paused', resumable: true } };
      }
      if (channel === 'runtime:pause') {
        state.calls.push({ channel, payload });
        return { attempt_id: payload.attempt_id, status: 'paused' };
      }
      return {};
    };
    (window as any).narrativeIDE = Object.fromEntries(Object.entries(bridgeMethods).map(([method, channel]) => [method, (payload: Record<string, unknown>) => invoke(channel, payload)]));
  }, TEST_NARRATIVE_IDE_INVOKE_METHODS);

  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();
  await page.getByTestId('w1-checkpoint-fork-checkpoint-resumable').click();
  await expect(page.getByTestId('w1-checkpoint-fork-error')).toContainText('active attempt was not changed');
  await page.getByTestId('w1-runtime-pause').click();
  await expect.poll(() => page.evaluate(() => (window as any).__missingForkSnapshotState.calls)).toEqual(expect.arrayContaining([
    expect.objectContaining({ channel: 'runtime:fork', payload: expect.objectContaining({ attempt_id: 'attempt-parent' }) }),
    expect.objectContaining({ channel: 'runtime:pause', payload: expect.objectContaining({ attempt_id: 'attempt-parent' }) }),
  ]));
});

test('shows a credential recovery action without exposing a credential to the renderer', async ({ page }) => {
  await page.addInitScript((bridgeMethods) => {
    const invoke = async (channel: string) => {
      if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
      if (channel === 'runtime:recoverable') return { runs: [{ lineage_id: 'lineage-1', attempt_id: 'attempt-1', status: 'recoverable', source_compatible: true }] };
      if (channel === 'runtime:events') return { events: [] };
      if (channel === 'runtime:checkpoints') return { checkpoints: [] };
      if (channel === 'runtime:resume') return { attempt_id: 'attempt-1', status: 'needs_credentials' };
      return {};
    };
    (window as any).narrativeIDE = Object.fromEntries(Object.entries(bridgeMethods).map(([method, channel]) => [method, () => invoke(channel)]));
  }, TEST_NARRATIVE_IDE_INVOKE_METHODS);

  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();
  await page.getByTestId('w1-recovery-resume-lineage-1').click();
  await expect(page.getByTestId('w1-recovery-needs-credentials')).toContainText('Add an API key');
});

test('requires a durable explicit decision before retrying or cancelling an unknown paid call', async ({ page }) => {
  await page.addInitScript((bridgeMethods) => {
    type Invocation = { channel: string; payload: Record<string, unknown> };
    const state = {
      calls: [] as Invocation[],
      decisionCalls: 0,
      retryDecision: 'pending',
      retryResumed: false,
      cancelDecision: 'pending',
    };
    (window as any).__unknownOutcomeState = state;

    const unknownCall = (kind: 'retry' | 'cancel') => ({
      tool_call_id: `call-${kind}`,
      idempotency_key: `${kind}-idempotency-key`,
      decision_key: `retry_provider_call:${kind}-idempotency-key`,
      safe_reason: 'transport_outcome_unknown',
      decision_state: kind === 'retry' ? state.retryDecision : state.cancelDecision,
    });
    const recoverableRuns = () => [
      ...(!state.retryResumed ? [{ lineage_id: 'lineage-retry', attempt_id: 'attempt-retry', status: 'waiting_human', source_compatible: true, unknown_calls: [unknownCall('retry')] }] : []),
      ...(state.cancelDecision !== 'cancel' ? [{ lineage_id: 'lineage-cancel', attempt_id: 'attempt-cancel', status: 'waiting_human', source_compatible: true, unknown_calls: [unknownCall('cancel')] }] : []),
    ];

    const invoke = async (channel: string, payload: Record<string, unknown> = {}) => {
      if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
      if (channel === 'runtime:recoverable') {
        state.calls.push({ channel, payload });
        return { runs: recoverableRuns() };
      }
      if (channel === 'runtime:events') return { events: [] };
      if (channel === 'runtime:checkpoints') return { checkpoints: [] };
      if (channel === 'runtime:decision') {
        state.calls.push({ channel, payload });
        state.decisionCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 120));
        if (payload.decision === 'authorize_retry_once') state.retryDecision = 'authorize_retry_once';
        if (payload.decision === 'cancel') state.cancelDecision = 'cancel';
        return { decision_key: payload.decision_key, decision: payload.decision, attempt_status: payload.decision === 'cancel' ? 'cancelled' : 'waiting_human' };
      }
      if (channel === 'runtime:resume') {
        state.calls.push({ channel, payload });
        state.retryResumed = true;
        return { lineage_id: 'lineage-retry', attempt_id: 'attempt-retry', status: 'resumed' };
      }
      if (channel === 'runtime:cancel') state.calls.push({ channel, payload });
      return {};
    };
    (window as any).narrativeIDE = Object.fromEntries(Object.entries(bridgeMethods).map(([method, channel]) => [method, (payload: Record<string, unknown>) => invoke(channel, payload)]));
  }, TEST_NARRATIVE_IDE_INVOKE_METHODS);

  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();

  await expect(page.getByTestId('w1-unknown-outcome-call-retry')).toContainText('Paid provider call has an unknown outcome');
  await expect(page.getByTestId('w1-unknown-outcome-call-retry')).toContainText('Connection ended before the outcome could be confirmed.');
  await expect(page.getByTestId('w1-recovery-resume-lineage-retry')).toBeDisabled();
  await page.evaluate(() => { (window as any).__unknownOutcomeState.calls = []; });

  const authorize = page.getByTestId('w1-unknown-authorize-call-retry');
  await authorize.click();
  await expect(authorize).toBeDisabled();
  await authorize.click({ force: true });
  await expect.poll(() => page.evaluate(() => (window as any).__unknownOutcomeState.decisionCalls)).toBe(1);
  await expect(page.getByTestId('w1-unknown-outcome-call-cancel')).toBeVisible();

  await expect.poll(() => page.evaluate(() => (window as any).__unknownOutcomeState.calls.map((entry: { channel: string }) => entry.channel))).toEqual([
    'runtime:decision',
    'runtime:recoverable',
    'runtime:resume',
    'runtime:recoverable',
  ]);
  const retryCalls = await page.evaluate(() => (window as any).__unknownOutcomeState.calls);
  expect(retryCalls[0].payload).toEqual({
    projectRoot: 'memory://starter-demo-project',
    decision_key: 'retry_provider_call:retry-idempotency-key',
    attempt_id: 'attempt-retry',
    decision: 'authorize_retry_once',
  });

  await page.evaluate(() => { (window as any).__unknownOutcomeState.calls = []; });
  await page.getByTestId('w1-unknown-cancel-call-cancel').click();
  await expect(page.getByTestId('w1-unknown-outcome-call-cancel')).toHaveCount(0);
  const cancelCalls = await page.evaluate(() => (window as any).__unknownOutcomeState.calls);
  expect(cancelCalls.map((entry: { channel: string }) => entry.channel)).toEqual(['runtime:decision', 'runtime:recoverable']);
  expect(cancelCalls[0].payload).toEqual({
    projectRoot: 'memory://starter-demo-project',
    decision_key: 'retry_provider_call:cancel-idempotency-key',
    attempt_id: 'attempt-cancel',
    decision: 'cancel',
  });
});
