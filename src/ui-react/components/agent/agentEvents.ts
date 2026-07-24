import type { RuntimeEvent } from '../import-runtime/types';

export type AgentEventKind =
  | 'plan'
  | 'agent'
  | 'tool'
  | 'chunk'
  | 'result'
  | 'retry'
  | 'cost'
  | 'recovery'
  | 'approval'
  | 'error';

export type AgentEventStatus = 'running' | 'completed' | 'failed' | 'blocked' | 'unknown_outcome' | 'recovering' | 'pending';

export interface AgentEventV1 {
  contractVersion: 'AgentEvent/v1';
  sourceContractVersion: string;
  id: string;
  sequence: number;
  timestamp?: string;
  kind: AgentEventKind;
  status: AgentEventStatus;
  actorId: string;
  actorKind: 'system' | 'planner' | 'agent' | 'tool' | 'human';
  title: string;
  summary: string;
  detail: string | null;
  tool: string | null;
  chunk: string | null;
  retry: string | null;
  costUsd: number | null;
  requiresAction: boolean;
  raw: RuntimeEvent;
}

const text = (value: unknown): string | null => {
  if (typeof value === 'string' && value.trim()) return value.trim();
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return null;
};

const pick = (payload: Record<string, unknown>, keys: string[]) => {
  for (const key of keys) {
    const value = text(payload[key]);
    if (value) return value;
  }
  return null;
};

const record = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;

const normalized = (event: RuntimeEvent) => event.event_type.toLowerCase().replace(/[.:-]/g, '_');

const statusFor = (value: string, payload: Record<string, unknown>): AgentEventStatus => {
  const status = (pick(payload, ['status', 'run_status', 'outcome']) ?? '').toLowerCase().replace(/[ -]/g, '_');
  if (status.includes('unknown')) return 'unknown_outcome';
  if (status.includes('block')) return 'blocked';
  if (status.includes('fail') || status.includes('error')) return 'failed';
  if (status.includes('recover')) return 'recovering';
  if (status.includes('complete') || status === 'done' || status === 'success') return 'completed';
  if (status.includes('pending') || status.includes('wait')) return 'pending';
  if (status.includes('run') || status.includes('start')) return 'running';
  if (/unknown_outcome|unknown_result/.test(value)) return 'unknown_outcome';
  if (/blocked|block/.test(value)) return 'blocked';
  if (/error|failed|failure|cancel/.test(value)) return 'failed';
  if (/recover|resume|restore/.test(value)) return 'recovering';
  if (/complete|completed|done|success|result/.test(value)) return 'completed';
  return 'running';
};

const kindFor = (value: string, payload: Record<string, unknown>): AgentEventKind => {
  const phase = (pick(payload, ['phase', 'stage', 'kind']) ?? '').toLowerCase().replace(/[.:-]/g, '_');
  const source = `${value}_${phase}`;
  if (/plan|planner|schedule|dag/.test(source)) return 'plan';
  if (/^tool_(completed|complete|result|finished|finish)$/.test(value)) return 'result';
  if (/^tool_(failed|failure|error)$/.test(value)) return 'error';
  if (/^tool_(started|start|intent|called|call)$/.test(value)) return 'tool';
  if (/retry|rerun|requeue|backoff/.test(source)) return 'retry';
  if (/cost|token|budget|usage/.test(source)) return 'cost';
  if (/recover|resume|restore|checkpoint|rewind|fork/.test(source)) return 'recovery';
  if (/approval|decision|human_gate|permission|authorize/.test(source)) return 'approval';
  if (/chunk|window|chapter/.test(source)) return 'chunk';
  if (/result|complete|output|artifact|receipt/.test(source)) return 'result';
  if (/error|failed|failure|blocked|cancel/.test(source)) return 'error';
  if (/tool|command|invoke/.test(source)) return 'tool';
  return 'agent';
};

const actorKindFor = (event: RuntimeEvent, payload: Record<string, unknown>, kind: AgentEventKind): AgentEventV1['actorKind'] => {
  const payloadActor = record(payload.actor);
  const actor = (
    text(event.actor?.kind)
    ?? text(payloadActor?.kind)
    ?? pick(payload, ['actor_kind', 'actorKind'])
    ?? ''
  ).toLowerCase();
  if (actor === 'planner' || actor === 'tool' || actor === 'human' || actor === 'system' || actor === 'agent') return actor;
  if (kind === 'plan') return 'planner';
  if (kind === 'tool') return 'tool';
  if (kind === 'approval') return 'human';
  return 'agent';
};

const planPresentation = (event: RuntimeEvent, payload: Record<string, unknown>) => {
  if (!normalized(event).startsWith('plan_')) return null;
  const plan = record(payload.plan);
  const planId = text(plan?.plan_id) ?? text(plan?.planId) ?? pick(payload, ['plan_id', 'planId']);
  const workflowId = text(plan?.workflow_id) ?? text(plan?.workflowId) ?? pick(payload, ['workflow_id', 'workflowId']);
  if (!planId && !workflowId) return null;
  return {
    title: planId ? `Plan ${planId}` : event.event_type,
    summary: workflowId ? `Workflow ${workflowId}` : `Plan ${planId}`,
  };
};

const safeReceiptSummary = (payload: Record<string, unknown>) => {
  const explicit = pick(payload, ['safe_summary', 'safeSummary', 'summary', 'message']);
  if (explicit) return explicit;
  const receipt = record(payload.receipt) ?? record(payload.artifact_receipt);
  if (!receipt) return null;
  const receiptId = pick(receipt, ['receipt_id', 'receiptId', 'artifact_id', 'artifactId', 'sha256']);
  const receiptStatus = pick(receipt, ['status', 'kind', 'contract_version', 'contractVersion']);
  return [receiptStatus, receiptId].filter(Boolean).join(' · ') || null;
};

export const normalizeAgentEvent = (event: RuntimeEvent): AgentEventV1 => {
  const payload = event.payload ?? {};
  const value = normalized(event);
  const kind = kindFor(value, payload);
  const status = statusFor(value, payload);
  const payloadActor = record(payload.actor);
  const actorId = text(event.actor?.id)
    ?? text(payloadActor?.id)
    ?? pick(payload, ['actor_id', 'actorId', 'agent_id', 'agentId', 'node_id', 'nodeId'])
    ?? 'runtime';
  const tool = pick(payload, ['tool_name', 'toolName', 'tool', 'command']);
  const chunk = pick(payload, ['chunk_id', 'chunkId', 'window_id', 'windowId', 'chapter_id', 'chapterId']);
  const retry = pick(payload, ['retry_count', 'retryCount', 'attempt', 'attempt_number', 'rerun_reason']);
  const cost = Number(payload.cost_usd ?? payload.costUsd ?? payload.api_cost_usd ?? payload.apiCostUsd);
  const requiresAction = Boolean(payload.requires_human_action ?? payload.requiresHumanAction ?? payload.requires_approval ?? payload.requiresApproval ?? payload.action_required ?? payload.actionRequired)
    || status === 'blocked' || status === 'unknown_outcome' || kind === 'approval';
  const planPresentationValue = planPresentation(event, payload);
  const isCompletedTool = /^tool_(completed|complete|result|finished|finish)$/.test(value);
  const summary = planPresentationValue?.summary
    ?? (isCompletedTool ? safeReceiptSummary(payload) : pick(payload, ['summary', 'message', 'detail', 'reason']))
    ?? event.event_type;
  const detail = isCompletedTool
    ? pick(payload, ['safe_detail', 'safeDetail', 'receipt_summary', 'receiptSummary'])
    : pick(payload, ['detail', 'reason', 'error', 'artifact_path', 'artifactPath']);
  return {
    contractVersion: 'AgentEvent/v1',
    sourceContractVersion: text(event.contract_version) ?? 'legacy/v0',
    id: event.event_id,
    sequence: event.sequence,
    timestamp: event.created_at,
    kind,
    status,
    actorId,
    actorKind: actorKindFor(event, payload, kind),
    title: planPresentationValue?.title ?? pick(payload, ['title', 'label', 'name']) ?? event.event_type,
    summary,
    detail,
    tool,
    chunk,
    retry,
    costUsd: Number.isFinite(cost) ? cost : null,
    requiresAction,
    raw: event,
  };
};

export const normalizeAgentEvents = (events: readonly RuntimeEvent[]) => events.map(normalizeAgentEvent).sort((a, b) => b.sequence - a.sequence);
