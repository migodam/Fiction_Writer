import { expect, test } from '@playwright/test';
import { normalizeAgentEvent } from '../../../src/ui-react/components/agent/agentEvents';
import type { RuntimeEvent } from '../../../src/ui-react/components/import-runtime/types';

const event = (overrides: Partial<RuntimeEvent>): RuntimeEvent => ({
  event_id: 'event-1',
  sequence: 1,
  event_type: 'agent.progress',
  payload: {},
  ...overrides,
});

test.describe('AgentEvent/v1 adapter', () => {
  test('prefers top-level v6 contract metadata and preserves the source contract', () => {
    const normalized = normalizeAgentEvent(event({
      contract_version: 'AgentEvent/v1',
      actor: { kind: 'tool', id: 'w1.extract.characters' },
      payload: {
        actor: { kind: 'agent', id: 'legacy-nested' },
        actor_id: 'legacy-flat',
        summary: 'Extracting character evidence',
      },
    }));

    expect(normalized.contractVersion).toBe('AgentEvent/v1');
    expect(normalized.sourceContractVersion).toBe('AgentEvent/v1');
    expect(normalized.actorKind).toBe('tool');
    expect(normalized.actorId).toBe('w1.extract.characters');
  });

  test('keeps legacy actor compatibility without relabelling its source as v1', () => {
    const normalized = normalizeAgentEvent(event({
      event_type: 'agent.progress',
      payload: { actor: { kind: 'agent', id: 'legacy-reviewer' } },
    }));

    expect(normalized.sourceContractVersion).toBe('legacy/v0');
    expect(normalized.actorKind).toBe('agent');
    expect(normalized.actorId).toBe('legacy-reviewer');
  });

  test('classifies completed tool events as results and started tool events as tools', () => {
    expect(normalizeAgentEvent(event({ event_type: 'tool.completed' })).kind).toBe('result');
    expect(normalizeAgentEvent(event({ event_type: 'tool.result' })).kind).toBe('result');
    expect(normalizeAgentEvent(event({ event_type: 'tool.started' })).kind).toBe('tool');
    expect(normalizeAgentEvent(event({ event_type: 'tool.intent' })).kind).toBe('tool');
  });

  test('builds readable plan labels from the typed plan payload', () => {
    const normalized = normalizeAgentEvent(event({
      event_type: 'plan.started',
      actor: { kind: 'planner', id: 'w1.planner' },
      payload: { plan: { plan_id: 'plan-42', workflow_id: 'W1' } },
    }));

    expect(normalized.kind).toBe('plan');
    expect(normalized.title).toBe('Plan plan-42');
    expect(normalized.summary).toBe('Workflow W1');
  });

  test('never exposes arbitrary raw tool results', () => {
    const normalized = normalizeAgentEvent(event({
      event_type: 'tool.completed',
      payload: {
        result: 'private provider response that must not render',
        detail: 'untrusted result detail',
        safe_summary: 'Character extraction receipt recorded',
        receipt: { receipt_id: 'receipt-7', status: 'verified' },
      },
    }));

    expect(normalized.summary).toBe('Character extraction receipt recorded');
    expect(normalized.detail).toBeNull();
    expect(JSON.stringify({ title: normalized.title, summary: normalized.summary, detail: normalized.detail })).not.toContain('private provider response');
    expect(JSON.stringify({ title: normalized.title, summary: normalized.summary, detail: normalized.detail })).not.toContain('untrusted result detail');
  });
});

test('Agent Dock localizes kind, status, and actor while retaining theme tokens', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.evaluate(() => {
    (window as any).__narrativeStore.setState({
      w1RuntimeEvents: [{
        contract_version: 'AgentEvent/v1',
        event_id: 'event-localized',
        sequence: 1,
        event_type: 'tool.completed',
        actor: { kind: 'tool', id: 'w1.extract.characters' },
        payload: {
          status: 'completed',
          tool_name: 'extract.characters',
          safe_summary: 'Character receipt recorded',
        },
      }],
    });
  });

  const item = page.getByTestId('agent-runtime-event-event-localized');
  await expect(item).toContainText('Result');
  await expect(item).toContainText('Completed');
  await expect(item).toContainText('Tool · w1.extract.characters');
  await expect(item.locator('span').first()).toHaveClass(/text-green/);

  await page.getByTestId('toolbar-settings').click();
  const settings = page.getByTestId('settings-modal');
  await expect(settings).toBeVisible();
  await settings.getByRole('button', { name: /^Chinese/ }).click();
  await expect(item).toContainText('结果');
  await expect(item).toContainText('已完成');
  await expect(item).toContainText('工具 · w1.extract.characters');
  await expect(item.locator('span').first()).toHaveClass(/text-green/);
});
