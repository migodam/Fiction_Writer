export type RuntimeUnknownCallDecision = 'authorize_retry_once' | 'cancel';

export interface RuntimeUnknownCall {
  tool_call_id: string;
  idempotency_key: string;
  decision_key: string;
  safe_reason: string;
  decision_state: 'pending' | RuntimeUnknownCallDecision | string;
}

export interface RuntimeRun {
  lineage_id: string;
  attempt_id?: string;
  status?: string;
  completed?: number;
  remaining?: number;
  source_compatible?: boolean | null;
  api_cost_usd?: number | null;
  summary?: string;
  unknown_calls?: RuntimeUnknownCall[];
  error?: string;
}

export interface RuntimeEvent {
  event_id: string;
  sequence: number;
  event_type: string;
  payload?: Record<string, unknown>;
  created_at?: string;
}

export interface RuntimeCheckpoint {
  checkpoint_id: string;
  sequence?: number;
  label?: string;
  summary?: string;
  created_at?: string;
}

export const runtimeAgentId = (event: RuntimeEvent) => {
  const payload = event.payload ?? {};
  return String(payload.agent_id ?? payload.agentId ?? payload.node_id ?? payload.nodeId ?? 'runtime');
};

export const runtimeSummary = (event: RuntimeEvent) => {
  const payload = event.payload ?? {};
  return String(payload.summary ?? payload.message ?? event.event_type);
};
