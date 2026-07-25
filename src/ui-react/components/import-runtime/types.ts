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
  contract_version?: string;
  actor?: {
    kind?: string;
    id?: string;
  } | null;
  run_id?: string;
  lineage_id?: string;
  attempt_id?: string;
  causation_id?: string | null;
  correlation_id?: string | null;
  idempotency_key?: string | null;
  payload?: Record<string, unknown>;
  created_at?: string;
}

export interface RuntimeCheckpoint {
  checkpoint_id: string;
  sequence?: number;
  label?: string;
  summary?: string;
  created_at?: string;
  /**
   * New runtime payloads put recovery capability here. The direct fields are
   * retained because an Electron bridge can be updated independently of the
   * sidecar and older projects may still return the pre-envelope shape.
   */
  metadata?: RuntimeCheckpointMetadata | Record<string, unknown> | string;
  resumable?: boolean;
  non_resumable_reason?: string;
  snapshot_ref?: RuntimeSnapshotRef | Record<string, unknown> | string;
}

export interface RuntimeSnapshotRef {
  contract_version: 'W1SupervisorSnapshot/v1';
  relative_path: string;
  manifest_sha256: string;
  snapshot_sha256: string;
  source_identity_sha256: string;
  config_identity_sha256: string;
  lineage_id: string;
  attempt_id: string;
  checkpoint_id: string;
  [key: string]: unknown;
}

export interface RuntimeCheckpointMetadata {
  resumable?: boolean;
  non_resumable_reason?: string;
  recovery_mode?: 'resumable' | 'preview_only' | string;
  preview_reason?: string;
  snapshot_error?: string;
  snapshot_ref?: RuntimeSnapshotRef | Record<string, unknown> | string;
  [key: string]: unknown;
}

export interface RuntimeCheckpointCapability {
  resumable: boolean;
  reason?: string;
  snapshotRef?: RuntimeSnapshotRef;
}

/**
 * The server returns a fork's proof inside its immutable state reference.
 * Keep this separate from checkpoint metadata: a child attempt must never be
 * considered resumable based on an unscoped top-level flag or reference.
 */
export interface RuntimeForkStateReference {
  kind?: 'w1_supervisor_snapshot/v1' | string;
  immutable?: boolean;
  resumable?: boolean;
  snapshot_ref?: RuntimeSnapshotRef | Record<string, unknown> | string;
  [key: string]: unknown;
}

export interface RuntimeForkSnapshot {
  resumable?: boolean;
  non_resumable_reason?: string;
  state_reference?: RuntimeForkStateReference | Record<string, unknown> | string;
  [key: string]: unknown;
}

const runtimeObject = (value: unknown): Record<string, unknown> | undefined => {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>;
  if (typeof value !== 'string') return undefined;
  try {
    const parsed = JSON.parse(value) as unknown;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : undefined;
  } catch {
    return undefined;
  }
};

const runtimeString = (value: unknown): string | undefined =>
  typeof value === 'string' && value.trim() ? value.trim() : undefined;

const SNAPSHOT_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const SNAPSHOT_HASH = /^[0-9a-f]{64}$/;

const safeSnapshotRelativePath = (value: unknown): value is string => {
  if (typeof value !== 'string' || !value || value.startsWith('/') || value.includes('\\') || value.includes('\0')) return false;
  const parts = value.split('/');
  return parts.length > 0 && parts.every((part) => part.length > 0 && part !== '.' && part !== '..');
};

/** Renderer proof only. The sidecar repeats this verification before resume. */
export const verifiedRuntimeSnapshotRef = (value: unknown): RuntimeSnapshotRef | undefined => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return undefined;
  const reference = value as Record<string, unknown>;
  if (
    reference.contract_version !== 'W1SupervisorSnapshot/v1'
    || !safeSnapshotRelativePath(reference.relative_path)
    || !SNAPSHOT_ID.test(String(reference.lineage_id ?? ''))
    || !SNAPSHOT_ID.test(String(reference.attempt_id ?? ''))
    || !SNAPSHOT_ID.test(String(reference.checkpoint_id ?? ''))
  ) return undefined;
  for (const field of ['manifest_sha256', 'snapshot_sha256', 'source_identity_sha256', 'config_identity_sha256'] as const) {
    if (!SNAPSHOT_HASH.test(String(reference[field] ?? ''))) return undefined;
  }
  return reference as RuntimeSnapshotRef;
};

/** Only the API's state_reference envelope is proof that a fork can resume. */
export const verifiedRuntimeForkSnapshotRef = (value: unknown): RuntimeSnapshotRef | undefined => {
  const fork = runtimeObject(value);
  const stateReference = runtimeObject(fork?.state_reference);
  if (
    !fork
    || fork.resumable !== true
    || !stateReference
    || stateReference.kind !== 'w1_supervisor_snapshot/v1'
    || stateReference.immutable !== true
    || stateReference.resumable !== true
  ) return undefined;
  return verifiedRuntimeSnapshotRef(stateReference.snapshot_ref);
};

/**
 * Treat missing capability data as preview-only. That is deliberately
 * fail-closed: legacy summary checkpoints do not contain replayable state.
 */
export const runtimeCheckpointCapability = (checkpoint: RuntimeCheckpoint): RuntimeCheckpointCapability => {
  const metadata = runtimeObject(checkpoint.metadata) ?? {};
  const snapshotRef = verifiedRuntimeSnapshotRef(metadata.snapshot_ref ?? checkpoint.snapshot_ref);
  const explicitResumable = metadata.resumable ?? checkpoint.resumable;
  const recoveryMode = runtimeString(metadata.recovery_mode);
  const hasSnapshot = snapshotRef !== undefined;
  const resumable = (explicitResumable === true || recoveryMode === 'resumable') && hasSnapshot;
  const reason = runtimeString(metadata.non_resumable_reason)
    ?? runtimeString(checkpoint.non_resumable_reason)
    ?? runtimeString(metadata.preview_reason)
    ?? runtimeString(metadata.snapshot_error);
  return { resumable, reason, snapshotRef };
};

export const runtimeAgentId = (event: RuntimeEvent) => {
  const payload = event.payload ?? {};
  return String(payload.agent_id ?? payload.agentId ?? payload.node_id ?? payload.nodeId ?? 'runtime');
};

export const runtimeSummary = (event: RuntimeEvent) => {
  const payload = event.payload ?? {};
  return String(payload.summary ?? payload.message ?? event.event_type);
};
