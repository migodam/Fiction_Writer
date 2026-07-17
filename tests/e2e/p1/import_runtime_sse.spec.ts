import { expect, test, type Page } from '@playwright/test';
import { TEST_NARRATIVE_IDE_INVOKE_METHODS } from '../helpers/narrativeIdeBridge';

type StreamEvent = {
  event_id: string;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
};

async function openRecovery(page: Page) {
  await page.goto('http://localhost:3000');
  await page.getByTestId('activity-btn-workbench').click();
  await page.getByTestId('open-import-btn').click();
  await expect(page.getByTestId('w1-recovery-center')).toBeVisible();
}

test('SSE reconnects from the contiguous cursor, replays a missing sequence, and dedupes', async ({ page }) => {
  await page.addInitScript((bridgeMethods) => {
    const eventListeners = new Set<(message: unknown) => void>();
    const statusListeners = new Set<(message: unknown) => void>();
    const state = { subscriptions: [] as Array<Record<string, unknown>>, unsubscriptions: [] as string[], eventPolls: 0 };
    (window as any).__runtimeSseState = state;
    const emitEvent = (message: unknown) => [...eventListeners].forEach((listener) => listener(message));
    const emitStatus = (message: unknown) => [...statusListeners].forEach((listener) => listener(message));
    const runtimeEvent = (sequence: number): StreamEvent => ({ event_id: `event-${sequence}`, sequence, event_type: 'agent.progress', payload: { agent_id: 'scout', summary: `Event ${sequence}` } });
    const invoke = async (channel: string) => {
      if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
      if (channel === 'runtime:recoverable') return { runs: [{ lineage_id: 'lineage-1', attempt_id: 'attempt-1', status: 'recoverable', source_compatible: true }] };
      if (channel === 'runtime:events') { state.eventPolls += 1; return { events: [] }; }
      if (channel === 'runtime:checkpoints') return { checkpoints: [] };
      if (channel === 'runtime:resume') return { attempt_id: 'attempt-2', status: 'running' };
      return {};
    };
    const bridge = Object.fromEntries(Object.entries(bridgeMethods).map(([method, channel]) => [method, () => invoke(channel)])) as Record<string, any>;
    bridge.onRuntimeEvent = (listener: (message: unknown) => void) => { eventListeners.add(listener); return () => eventListeners.delete(listener); };
    bridge.onRuntimeEventStreamStatus = (listener: (message: unknown) => void) => { statusListeners.add(listener); return () => statusListeners.delete(listener); };
    bridge.runtimeEventStreamUnsubscribe = async ({ subscription_id }: { subscription_id: string }) => { state.unsubscriptions.push(subscription_id); return { ok: true }; };
    bridge.runtimeEventStreamSubscribe = async (payload: Record<string, unknown>) => {
      state.subscriptions.push(payload);
      const call = state.subscriptions.length;
      queueMicrotask(() => {
        const envelope = { subscription_id: payload.subscription_id, attempt_id: payload.attempt_id };
        emitStatus({ ...envelope, status: 'open' });
        if (call === 1) {
          emitEvent({ ...envelope, event: runtimeEvent(1) });
          emitStatus({ ...envelope, status: 'closed', retryable: true });
        } else if (call === 2) {
          emitEvent({ ...envelope, event: runtimeEvent(3) });
        } else if (call === 3) {
          emitEvent({ ...envelope, event: runtimeEvent(2) });
          emitEvent({ ...envelope, event: runtimeEvent(3) });
        }
      });
      return { ok: true, subscription_id: payload.subscription_id };
    };
    (window as any).narrativeIDE = bridge;
  }, TEST_NARRATIVE_IDE_INVOKE_METHODS);

  await openRecovery(page);
  await expect.poll(() => page.evaluate(() => (window as any).__runtimeSseState.subscriptions.map((entry: any) => entry.after_sequence))).toEqual([0, 1, 1]);
  await expect(page.getByTestId('w1-runtime-agent-scout')).toBeVisible();
  await expect.poll(() => page.evaluate(() => (window as any).__narrativeStore.getState().w1RuntimeEvents.map((event: StreamEvent) => [event.event_id, event.sequence]))).toEqual([
    ['event-1', 1],
    ['event-2', 2],
    ['event-3', 3],
  ]);
  await expect.poll(() => page.evaluate(() => (window as any).__runtimeSseState.eventPolls)).toBe(0);
  const activeSubscriptionId = await page.evaluate(() => (window as any).__runtimeSseState.subscriptions.at(-1).subscription_id);
  await page.getByTestId('w1-recovery-resume-lineage-1').click();
  await expect.poll(() => page.evaluate(() => (window as any).__runtimeSseState.subscriptions.at(-1).attempt_id)).toBe('attempt-2');
  await expect.poll(() => page.evaluate((id) => (window as any).__runtimeSseState.unsubscriptions.includes(id), activeSubscriptionId)).toBe(true);
});

test('falls back to durable event polling after three consecutive SSE failures', async ({ page }) => {
  await page.addInitScript((bridgeMethods) => {
    const eventListeners = new Set<(message: unknown) => void>();
    const statusListeners = new Set<(message: unknown) => void>();
    const state = { streamCalls: 0, eventPolls: 0 };
    (window as any).__runtimeSseFallbackState = state;
    const invoke = async (channel: string) => {
      if (channel === 'sidecar:spawn') return { ok: true, port: 8765 };
      if (channel === 'runtime:recoverable') return { runs: [{ lineage_id: 'lineage-1', attempt_id: 'attempt-1', status: 'recoverable', source_compatible: true }] };
      if (channel === 'runtime:events') {
        state.eventPolls += 1;
        return { events: [{ event_id: 'poll-event-1', sequence: 1, event_type: 'agent.progress', payload: { agent_id: 'reviewer', summary: 'Polling recovered' } }] };
      }
      if (channel === 'runtime:checkpoints') return { checkpoints: [] };
      return {};
    };
    const bridge = Object.fromEntries(Object.entries(bridgeMethods).map(([method, channel]) => [method, () => invoke(channel)])) as Record<string, any>;
    bridge.onRuntimeEvent = (listener: (message: unknown) => void) => { eventListeners.add(listener); return () => eventListeners.delete(listener); };
    bridge.onRuntimeEventStreamStatus = (listener: (message: unknown) => void) => { statusListeners.add(listener); return () => statusListeners.delete(listener); };
    bridge.runtimeEventStreamUnsubscribe = async () => ({ ok: true });
    bridge.runtimeEventStreamSubscribe = async (payload: Record<string, unknown>) => {
      state.streamCalls += 1;
      queueMicrotask(() => [...statusListeners].forEach((listener) => listener({ subscription_id: payload.subscription_id, attempt_id: payload.attempt_id, status: 'error', retryable: true, error: 'disconnected' })));
      return { ok: true, subscription_id: payload.subscription_id };
    };
    (window as any).narrativeIDE = bridge;
  }, TEST_NARRATIVE_IDE_INVOKE_METHODS);

  await openRecovery(page);
  await expect.poll(() => page.evaluate(() => (window as any).__runtimeSseFallbackState.streamCalls)).toBe(3);
  await expect.poll(() => page.evaluate(() => (window as any).__runtimeSseFallbackState.eventPolls)).toBeGreaterThan(0);
  await expect(page.getByTestId('w1-runtime-agent-reviewer')).toBeVisible();
});
