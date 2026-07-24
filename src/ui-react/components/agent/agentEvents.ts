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
  if (/retry|rerun|requeue|backoff/.test(source)) return 'retry';
  if (/cost|token|budget|usage/.test(source)) return 'cost';
  if (/recover|resume|restore|checkpoint|rewind|fork/.test(source)) return 'recovery';
  if (/approval|decision|human_gate|permission|authorize/.test(source)) return 'approval';
  if (/chunk|window|chapter/.test(source)) return 'chunk';
  if (/tool|command|invoke/.test(source)) return 'tool';
  if (/result|complete|output|artifact|receipt/.test(source)) return 'result';
  if (/error|failed|failure|blocked|cancel/.test(source)) return 'error';
  return 'agent';
};

const actorKindFor = (payload: Record<string, unknown>, kind: AgentEventKind): AgentEventV1['actorKind'] => {
  const actor = (pick(payload, ['actor_kind', 'actorKind']) ?? '').toLowerCase();
  if (actor === 'planner' || actor === 'tool' || actor === 'human' || actor === 'system' || actor === 'agent') return actor;
  if (kind === 'plan') return 'planner';
  if (kind === 'tool') return 'tool';
  if (kind === 'approval') return 'human';
  return 'agent';
};

export const normalizeAgentEvent = (event: RuntimeEvent): AgentEventV1 => {
  const payload = event.payload ?? {};
  const value = normalized(event);
  const kind = kindFor(value, payload);
  const status = statusFor(value, payload);
  const actorId = pick(payload, ['actor_id', 'actorId', 'agent_id', 'agentId', 'node_id', 'nodeId']) ?? 'runtime';
  const tool = pick(payload, ['tool_name', 'toolName', 'tool', 'command']);
  const chunk = pick(payload, ['chunk_id', 'chunkId', 'window_id', 'windowId', 'chapter_id', 'chapterId']);
  const retry = pick(payload, ['retry_count', 'retryCount', 'attempt', 'attempt_number', 'rerun_reason']);
  const cost = Number(payload.cost_usd ?? payload.costUsd ?? payload.api_cost_usd ?? payload.apiCostUsd);
  const requiresAction = Boolean(payload.requires_human_action ?? payload.requiresHumanAction ?? payload.requires_approval ?? payload.requiresApproval ?? payload.action_required ?? payload.actionRequired)
    || status === 'blocked' || status === 'unknown_outcome' || kind === 'approval';
  const summary = pick(payload, ['summary', 'message', 'detail', 'reason']) ?? event.event_type;
  return {
    contractVersion: 'AgentEvent/v1',
    id: event.event_id,
    sequence: event.sequence,
    timestamp: event.created_at,
    kind,
    status,
    actorId,
    actorKind: actorKindFor(payload, kind),
    title: pick(payload, ['title', 'label', 'name']) ?? event.event_type,
    summary,
    detail: pick(payload, ['detail', 'reason', 'error', 'artifact_path', 'artifactPath']),
    tool,
    chunk,
    retry,
    costUsd: Number.isFinite(cost) ? cost : null,
    requiresAction,
    raw: event,
  };
};

export const normalizeAgentEvents = (events: readonly RuntimeEvent[]) => events.map(normalizeAgentEvent).sort((a, b) => b.sequence - a.sequence);
