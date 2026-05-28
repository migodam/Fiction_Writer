export interface PickDirectoryResult {
  canceled: boolean;
  path: string | null;
}

export interface ProviderConnectionResult {
  ok: boolean;
  message: string;
}

export interface W3StartPayload {
  projectRoot: string;
  scene_id: string;
  task: string;
  hitl_mode: 'direct_output' | 'three_options';
  metadata_file_id?: string;
  api_key: string;
  model: string;
  endpoint: string;
}

export interface W3StartResult {
  status: 'done' | 'waiting' | 'error';
  output?: string;
  options?: string[];
  session_id?: string;
  error?: string;
}

export interface W3SelectResult {
  status: 'done' | 'error';
  output?: string;
  error?: string;
}

export interface W3StatusResult {
  status: string;
  progress: number;
  workflow_id: string | null;
}

export interface W3ProgressEvent {
  workflow_id: string;
  progress: number;
  message: string;
}

// ── W1 Import ────────────────────────────────────────────────────────────────

export type W1PromptProfile = 'fast' | 'balanced' | 'deep' | 'custom';

export interface W1CustomProfileConfig {
  quality_target: 'draft' | 'standard' | 'high' | 'max';
  chapters_per_window_min: number;
  chapters_per_window_max: number;
  max_chapters_per_window: number;
  character_granularity: 'major_only' | 'named_only' | 'all';
  event_density: 'arc_level' | 'chapter_level' | 'scene_level';
  timeline_topology_depth: 'flat' | 'branched' | 'full_dag';
  world_strictness: 'named_only' | 'with_description' | 'full_attributes';
  validation_strictness: 'off' | 'per_window' | 'per_arc';
  rerun_budget: number;
  max_rerun_iterations: number;
  judge_pass_threshold: number;
  language_policy: 'preserve_source' | 'normalize_to_source' | 'allow_mixed';
  input_window_budget: number;
  output_token_budget: number;
}

export interface W1OrchestratorOverrides {
  use_orchestrator: boolean;
  use_supervisor: boolean;
  rerun_budget: number;
  judge_pass_threshold: number;
  quality_target: W1CustomProfileConfig['quality_target'];
  language_policy: W1CustomProfileConfig['language_policy'];
}

export interface W1StartPayload {
  projectRoot: string;
  source_file_path: string;
  import_mode?: 'import_content_only' | 'import_all';
  prompt_profile?: W1PromptProfile;
  use_supervisor?: boolean;
  use_orchestrator?: boolean;
  custom_profile_config?: W1CustomProfileConfig;
  orchestrator_overrides?: W1OrchestratorOverrides;
  api_key?: string;
  model?: string;
  endpoint?: string;
}

export interface W1StartResult {
  session_id: string;
  status: string;
}

export interface W1CancelPayload {
  session_id: string;
}

export interface W1StatusResult {
  status: string;
  progress: number;
  errors: string[];
  completed_chunks: number;
  total_chunks: number;
  current_step?: string;
  prompt_profile?: W1PromptProfile;
  proposals_count?: number;
  import_review_report?: W1ImportReviewReport;
  current_tool?: string;
  current_window?: string | number;
  chapter_range?: string | { start?: string; end?: string };
  orchestrator_phase?: string;
  judge_score?: number;
  rerun_reason?: string;
  converge_status?: string;
  judge_artifact_summary?: W1JudgeArtifactSummary;
  last_activity_at?: string;
  last_activity_message?: string;
  active_api_calls?: number;
  elapsed_seconds?: number;
  idle_seconds?: number;
  cancel_requested?: boolean;
}

export interface W1ImportReviewReport {
  import_run_id?: string;
  status?: 'pass' | 'warning' | 'fail' | 'acceptable_with_warnings';
  warnings?: string[];
  errors?: string[];
  proposal_counts?: Record<string, number>;
  safe_accept_ids?: string[];
  blocked_ids?: string[];
  failed_chunks?: Array<{ chunk_id?: number; errors?: string[] }>;
  duplicate_merges?: Array<Record<string, unknown>>;
  low_confidence_items?: Array<Record<string, unknown>>;
  model?: string;
  prompt_profile?: W1PromptProfile;
  artifact_paths?: Record<string, string>;
  judge_artifact_summary?: W1JudgeArtifactSummary;
  judge_artifact?: W1JudgeArtifactSummary;
}

export interface W1JudgeArtifactSummary {
  status?: string;
  score?: number;
  judge_score?: number;
  converge_status?: string;
  rerun_reason?: string;
  summary?: string;
  strengths?: string[];
  risks?: string[];
  required_reruns?: string[];
  recommendations?: string[];
}

export interface ChunkLogEntry {
  chunk_id: number;
  total_chunks: number;
  step: string;
  new_characters: number;
  updated_characters: number;
  new_events: number;
  new_world: number;
  duration_ms: number;
  excerpt: string;
  errors: string[];
  timestamp: string;
}

export interface W1ActivityEntry {
  id: number;
  timestamp: string;
  level: 'info' | 'warning' | 'error' | string;
  phase: string;
  tool: string;
  window_id?: string;
  chapter_range?: string;
  prompt_label?: string;
  status: 'start' | 'success' | 'retry' | 'fail' | 'skip' | 'heartbeat' | 'cancelled' | string;
  message: string;
  elapsed_ms?: number;
  duration_ms?: number | null;
  completed?: number | null;
  total?: number | null;
  active_api_calls?: number;
  error?: string;
}

export interface W1ConsoleResult {
  entries: ChunkLogEntry[];
  activity_entries: W1ActivityEntry[];
  paused: boolean;
  breakpoint_chunk: number | null;
}

// ── W2 Manuscript Sync ───────────────────────────────────────────────────────

export interface W2StartPayload {
  projectRoot: string;
  mode: string;
  target_chapter_id?: string;
  api_key?: string;
  model?: string;
  endpoint?: string;
}

export interface W2StartResult {
  session_id: string;
  status: string;
  error?: string;
}

export interface W2StatusResult {
  status: string;
  progress: number;
  errors: string[];
  proposals_count: number;
}

// ── W4 Consistency Check ─────────────────────────────────────────────────────

export interface W4StartPayload {
  projectRoot: string;
  scope: string;
  target_id: string;
  api_key?: string;
  model?: string;
  endpoint?: string;
}

export interface W4StartResult {
  session_id: string;
  status: string;
}

export interface W4StatusResult {
  status: string;
  progress: number;
  issues: any[];
  severity_counts: Record<string, number>;
  errors: string[];
}

// ── W5 Simulation Engine ─────────────────────────────────────────────────────

export interface W5StartPayload {
  projectRoot: string;
  scenario_variable: string;
  affected_chapter_ids: string[];
  engines_selected: string[];
  api_key?: string;
  model?: string;
  endpoint?: string;
}

export interface W5StartResult {
  session_id: string;
  status: string;
}

export interface W5StatusResult {
  status: string;
  progress: number;
  report_markdown: string;
  engine_results: Record<string, any>;
  errors: string[];
}

// ── W6 Beta Reader ───────────────────────────────────────────────────────────

export interface W6StartPayload {
  projectRoot: string;
  persona_id: string;
  target_chapter_ids: string[];
  api_key?: string;
  model?: string;
  endpoint?: string;
}

export interface W6StartResult {
  session_id: string;
  status: string;
}

export interface W6StatusResult {
  status: string;
  progress: number;
  report_markdown: string;
  feedback_items: any[];
  errors: string[];
}

// ── W7 Metadata Ingestion ────────────────────────────────────────────────────

export interface MetadataIngestPayload {
  projectRoot: string;
  source_file_path: string;
  file_type: string;
  api_key?: string;
  model?: string;
  endpoint?: string;
}

export interface MetadataIngestResult {
  file_id: string;
  session_id: string;
  status: string;
}

export interface MetadataStatusResult {
  status: string;
  progress: number;
  file_id: string;
  vector_store_updated: boolean;
  errors: string[];
}

// ── Orchestrator ─────────────────────────────────────────────────────────────

export interface OrchestratorStartPayload {
  projectRoot: string;
  goal: string;
  auto_apply_threshold?: number;
  api_key?: string;
  model?: string;
  endpoint?: string;
}

export interface OrchestratorStartResult {
  session_id: string;
  status: string;
  plan: any[];
}

export interface OrchestratorStatusResult {
  status: string;
  current_step: number;
  total_steps: number;
  progress: number;
  pending_permission: any | null;
  plan?: any[];
  errors?: string[];
}

const getIpcRenderer = () => {
  const scope = globalThis as typeof globalThis & { require?: NodeRequire };
  const loader = scope.require;
  if (!loader) {
    return null;
  }

  try {
    return loader('electron').ipcRenderer as {
      invoke: (channel: string, payload?: unknown) => Promise<unknown>;
      send: (channel: string, payload?: unknown) => void;
      on: (channel: string, listener: (...args: unknown[]) => void) => void;
      removeAllListeners: (channel: string) => void;
    };
  } catch {
    return null;
  }
};

export const electronApi = {
  isAvailable(): boolean {
    return Boolean(getIpcRenderer());
  },

  async pickDirectory(mode: 'create' | 'open'): Promise<PickDirectoryResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) {
      return { canceled: true, path: null };
    }

    const result = (await ipcRenderer.invoke('dialog:pick-directory', { mode })) as PickDirectoryResult;
    return result;
  },

  async loadAppSettings<T = Record<string, unknown> | null>(): Promise<T | null> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) {
      return null;
    }
    return (await ipcRenderer.invoke('settings:load-app')) as T | null;
  },

  async saveAppSettings<T = Record<string, unknown>>(payload: Partial<T>): Promise<T | null> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) {
      return null;
    }
    return (await ipcRenderer.invoke('settings:save-app', payload)) as T | null;
  },

  async pickFiles(options?: { filters?: Array<{ name: string; extensions: string[] }>; multiple?: boolean }): Promise<string[]> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return [];
    const result = (await ipcRenderer.invoke('dialog:pick-files', options)) as { canceled: boolean; paths: string[] } | null;
    return result?.paths ?? [];
  },

  async testProviderConnection(payload: Record<string, unknown>): Promise<ProviderConnectionResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) {
      return { ok: false, message: 'ipc_unavailable' };
    }
    return (await ipcRenderer.invoke('settings:test-provider', payload)) as ProviderConnectionResult;
  },

  async aiChat(messages: Array<{ role: string; content: string }>): Promise<string> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return '';
    return (await ipcRenderer.invoke('ai:chat', { messages })) as string;
  },

  async aiGenerateImage(prompt: string): Promise<string> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return '';
    return (await ipcRenderer.invoke('ai:generate-image', { prompt })) as string;
  },

  async portraitSave(projectRoot: string, characterId: string, imageData: string): Promise<string> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return '';
    return (await ipcRenderer.invoke('portrait:save', { projectRoot, characterId, imageData })) as string;
  },

  async portraitUpload(projectRoot: string, characterId: string, sourcePath: string): Promise<string> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return '';
    return (await ipcRenderer.invoke('portrait:upload', { projectRoot, characterId, sourcePath })) as string;
  },

  aiStreamStart(requestId: string, messages: Array<{ role: string; content: string }>): void {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return;
    ipcRenderer.send('ai:stream-start', { requestId, messages });
  },

  aiStreamCancel(requestId: string): void {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return;
    ipcRenderer.send('ai:stream-cancel', { requestId });
  },

  onAIChunk(requestId: string, callback: (text: string) => void): () => void {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return () => {};
    const channel = `ai:chunk:${requestId}`;
    ipcRenderer.on(channel, (_event: unknown, text: unknown) => callback(text as string));
    return () => ipcRenderer.removeAllListeners(channel);
  },

  onAIDone(requestId: string, callback: () => void): () => void {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return () => {};
    const channel = `ai:done:${requestId}`;
    ipcRenderer.on(channel, () => callback());
    return () => ipcRenderer.removeAllListeners(channel);
  },

  onAIError(requestId: string, callback: (msg: string) => void): () => void {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return () => {};
    const channel = `ai:error:${requestId}`;
    ipcRenderer.on(channel, (_event: unknown, msg: unknown) => callback(msg as string));
    return () => ipcRenderer.removeAllListeners(channel);
  },

  // DB methods
  async dbOpen(projectRoot: string, projectJson?: unknown): Promise<{ ok: boolean }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false };
    return (await ipcRenderer.invoke('db:open', { projectRoot, projectJson })) as { ok: boolean };
  },

  async dbClose(projectRoot: string): Promise<{ ok: boolean }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false };
    return (await ipcRenderer.invoke('db:close', { projectRoot })) as { ok: boolean };
  },

  async dbUpsert(projectRoot: string, table: string, id: string, data: unknown): Promise<{ ok: boolean }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false };
    return (await ipcRenderer.invoke('db:upsert', { projectRoot, table, id, data })) as { ok: boolean };
  },

  async dbGetAll(projectRoot: string, table: string): Promise<unknown[]> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return [];
    return (await ipcRenderer.invoke('db:getAll', { projectRoot, table })) as unknown[];
  },

  async dbDelete(projectRoot: string, table: string, id: string): Promise<{ ok: boolean }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false };
    return (await ipcRenderer.invoke('db:delete', { projectRoot, table, id })) as { ok: boolean };
  },

  async dbSearch(projectRoot: string, query: string): Promise<Array<{ entity_type: string; entity_id: string; title: string }>> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return [];
    return (await ipcRenderer.invoke('db:search', { projectRoot, query })) as Array<{ entity_type: string; entity_id: string; title: string }>;
  },

  async w3Start(payload: W3StartPayload): Promise<W3StartResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'error', error: 'ipc_unavailable' };
    return (await ipcRenderer.invoke('w3:start', payload)) as W3StartResult;
  },

  async w3Select(projectRoot: string, sessionId: string, selectedOption: number): Promise<W3SelectResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'error' };
    return (await ipcRenderer.invoke('w3:select', { projectRoot, sessionId, selectedOption })) as W3SelectResult;
  },

  async w3Status(projectRoot: string): Promise<W3StatusResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'offline', progress: 0, workflow_id: null };
    return (await ipcRenderer.invoke('w3:status', { projectRoot })) as W3StatusResult;
  },

  onW3Progress(callback: (event: W3ProgressEvent) => void): () => void {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return () => {};
    ipcRenderer.on('w3:progress', (_event: unknown, data: unknown) => callback(data as W3ProgressEvent));
    return () => ipcRenderer.removeAllListeners('w3:progress');
  },

  // ── W1 Import ─────────────────────────────────────────────────────────────

  async w1Start(payload: W1StartPayload): Promise<W1StartResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { session_id: '', status: 'error' };
    return (await ipcRenderer.invoke('w1:start', payload)) as W1StartResult;
  },

  async w1Cancel(payload: W1CancelPayload): Promise<{ status: string }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'error' };
    return (await ipcRenderer.invoke('w1:cancel', payload)) as { status: string };
  },

  async w1Status(projectRoot: string, sessionId?: string): Promise<W1StatusResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'offline', progress: 0, errors: [], completed_chunks: 0, total_chunks: 0 };
    return (await ipcRenderer.invoke('w1:status', { projectRoot, session_id: sessionId })) as W1StatusResult;
  },

  async w1Console(projectRoot: string, sessionId: string, after = 0, activityAfter = 0): Promise<W1ConsoleResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { entries: [], activity_entries: [], paused: false, breakpoint_chunk: null };
    return (await ipcRenderer.invoke('w1:console', { projectRoot, session_id: sessionId, after, activity_after: activityAfter })) as W1ConsoleResult;
  },

  async w1SetBreakpoint(projectRoot: string, sessionId: string, chunkId: number | null): Promise<{ ok: boolean }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false };
    return (await ipcRenderer.invoke('w1:set_breakpoint', { projectRoot, session_id: sessionId, chunk_id: chunkId })) as { ok: boolean };
  },

  async w1Resume(projectRoot: string, sessionId: string): Promise<{ ok: boolean }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false };
    return (await ipcRenderer.invoke('w1:resume', { projectRoot, session_id: sessionId })) as { ok: boolean };
  },

  async w1Rewind(projectRoot: string, sessionId: string, toChunkId: number): Promise<{ ok: boolean; new_session_id?: string }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false };
    return (await ipcRenderer.invoke('w1:rewind', { projectRoot, session_id: sessionId, to_chunk_id: toChunkId })) as { ok: boolean; new_session_id?: string };
  },

  async fetchPrompts(projectRoot: string): Promise<Record<string, { name: string; text: string }[]>> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return {};
    return (await ipcRenderer.invoke('prompts:list', { projectRoot })) as Record<string, { name: string; text: string }[]>;
  },

  async sidecarSpawn(projectRoot: string): Promise<{ ok: boolean; port: number }> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { ok: false, port: 0 };
    return (await ipcRenderer.invoke('sidecar:spawn', { projectRoot })) as { ok: boolean; port: number };
  },

  // ── W2 Manuscript Sync ────────────────────────────────────────────────────

  async w2Start(payload: W2StartPayload): Promise<W2StartResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { session_id: '', status: 'error' };
    return (await ipcRenderer.invoke('w2:start', payload)) as W2StartResult;
  },

  async w2Status(projectRoot: string, sessionId: string): Promise<W2StatusResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'error', progress: 0, errors: ['ipc_unavailable'], proposals_count: 0 };
    return (await ipcRenderer.invoke('w2:status', { projectRoot, session_id: sessionId })) as W2StatusResult;
  },

  // ── W4 Consistency Check ──────────────────────────────────────────────────

  async w4Start(payload: W4StartPayload): Promise<W4StartResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { session_id: '', status: 'error' };
    return (await ipcRenderer.invoke('w4:start', payload)) as W4StartResult;
  },

  async w4Status(projectRoot: string, sessionId: string): Promise<W4StatusResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'error', progress: 0, issues: [], severity_counts: {}, errors: [] };
    return (await ipcRenderer.invoke('w4:status', { projectRoot, session_id: sessionId })) as W4StatusResult;
  },

  // ── W5 Simulation Engine ──────────────────────────────────────────────────

  async w5Start(payload: W5StartPayload): Promise<W5StartResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { session_id: '', status: 'error' };
    return (await ipcRenderer.invoke('w5:start', payload)) as W5StartResult;
  },

  async w5Status(projectRoot: string, sessionId: string): Promise<W5StatusResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'error', progress: 0, report_markdown: '', engine_results: {}, errors: [] };
    return (await ipcRenderer.invoke('w5:status', { projectRoot, session_id: sessionId })) as W5StatusResult;
  },

  // ── W6 Beta Reader ────────────────────────────────────────────────────────

  async w6Start(payload: W6StartPayload): Promise<W6StartResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { session_id: '', status: 'error' };
    return (await ipcRenderer.invoke('w6:start', payload)) as W6StartResult;
  },

  async w6Status(projectRoot: string, sessionId: string): Promise<W6StatusResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'error', progress: 0, report_markdown: '', feedback_items: [], errors: [] };
    return (await ipcRenderer.invoke('w6:status', { projectRoot, session_id: sessionId })) as W6StatusResult;
  },

  // ── W7 Metadata Ingestion ─────────────────────────────────────────────────

  async metadataIngest(payload: MetadataIngestPayload): Promise<MetadataIngestResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { file_id: '', session_id: '', status: 'error' };
    return (await ipcRenderer.invoke('metadata:ingest', payload)) as MetadataIngestResult;
  },

  async metadataStatus(projectRoot: string, sessionId: string): Promise<MetadataStatusResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'error', progress: 0, file_id: '', vector_store_updated: false, errors: [] };
    return (await ipcRenderer.invoke('metadata:status', { projectRoot, session_id: sessionId })) as MetadataStatusResult;
  },

  // ── Orchestrator ──────────────────────────────────────────────────────────

  async orchestratorStart(payload: OrchestratorStartPayload): Promise<OrchestratorStartResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { session_id: '', status: 'error', plan: [] };
    return (await ipcRenderer.invoke('orchestrator:start', payload)) as OrchestratorStartResult;
  },

  async orchestratorStatus(projectRoot: string, sessionId: string): Promise<OrchestratorStatusResult> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'offline', current_step: 0, total_steps: 0, progress: 0, pending_permission: null };
    return (await ipcRenderer.invoke('orchestrator:status', { projectRoot, session_id: sessionId })) as OrchestratorStatusResult;
  },

  async orchestratorGrant(projectRoot: string, stepId: string, sessionId: string): Promise<any> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'error' };
    return ipcRenderer.invoke('orchestrator:grant', { projectRoot, stepId, session_id: sessionId });
  },

  async orchestratorDeny(projectRoot: string, stepId: string, sessionId: string, reason: string): Promise<any> {
    const ipcRenderer = getIpcRenderer();
    if (!ipcRenderer) return { status: 'error' };
    return ipcRenderer.invoke('orchestrator:deny', { projectRoot, stepId, session_id: sessionId, reason });
  },
};
